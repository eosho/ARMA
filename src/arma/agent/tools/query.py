"""Query tools for Azure resource operations.

This module provides tools for listing, getting, and deleting Azure resources.
"""

import json
import subprocess

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from arma.core.logging import get_logger

logger = get_logger(__name__)


@tool
async def list_resources(
    runtime: ToolRuntime,
    resource_type: str | None = None,
    location: str | None = None,
    resource_group: str | None = None,
    tags: str | None = None,
) -> Command:
    """List Azure resources by type with optional filters.

    Query Azure resources by their type (e.g., Microsoft.Storage/storageAccounts).
    Results can be filtered by location, resource group, or tags.

    Args:
        resource_type: Azure resource type (e.g., 'Microsoft.Storage/storageAccounts')
        runtime: Tool runtime context (injected automatically)
        location: Filter by Azure region (e.g., 'eastus', 'westus2')
        resource_group: Filter by resource group name
        tags: Filter by tags in format 'key1=value1 key2=value2'

    Returns:
        Command with updated state (query_results, last_query) and ToolMessage

    Examples:
        >>> # List all resources
        >>> result = await list_resources()

        >>> # List all resources in rg test-rg-01
        >>> result = await list_resources(resource_group="test-rg-01")

        >>> # List all storage accounts in subscription
        >>> result = await list_resources("Microsoft.Storage/storageAccounts")

        >>> # List VMs in specific location
        >>> result = await list_resources("Microsoft.Compute/virtualMachines", location="eastus")

        >>> # List resources in specific resource group
        >>> result = await list_resources("Microsoft.Storage/storageAccounts", resource_group="prod-rg")
    """
    subscription_id = runtime.state.get("subscription_id")
    if not subscription_id:
        logger.warning("subscription_id not found in state - asking user to provide it")
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            "Cannot list resources: subscription_id not set in state. "
                            "Please ask the user to provide their Azure subscription ID, "
                            "or they can mention it in their request (e.g., 'in subscription abc-123...')."
                        ),
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    logger.info(f"Listing resources in subscription {subscription_id}")

    # Build Azure CLI command
    cmd = [
        "az",
        "resource",
        "list",
        "--subscription",
        subscription_id,
        "--query",
        "[].{name:name, location:location, resourceGroup:resourceGroup, id:id, type:type, tags:tags}",
        "-o",
        "json",
    ]

    # Add optional filters
    if resource_type:
        logger.info(f"Listing resources of type {resource_type}")
        cmd.extend(["--resource-type", resource_type])
        logger.debug(f"Filtering by resource type: {resource_type}")

    if location:
        cmd.extend(["--location", location])
        logger.debug(f"Filtering by location: {location}")

    if resource_group:
        cmd.extend(["--resource-group", resource_group])
        logger.debug(f"Filtering by resource group: {resource_group}")

    if tags:
        cmd.extend(["--tag", tags])
        logger.debug(f"Filtering by tags: {tags}")

    try:
        logger.debug(f"Executing command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)

        resources = json.loads(result.stdout)
        logger.info(f"Found {len(resources)} resources")

        # Return Command with state updates and ToolMessage
        return Command(
            update={
                "query_results": resources,
                "last_query": {
                    "resource_type": resource_type,
                    "location": location,
                    "resource_group": resource_group,
                    "count": len(resources),
                },
                "messages": [
                    ToolMessage(
                        content=f"Found {len(resources)} resources. Details {resources} ",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to list resources: {e.stderr}")
        raise RuntimeError(f"Failed to list resources: {e.stderr}")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Azure CLI output: {e}")
        raise RuntimeError(f"Failed to parse Azure CLI output: {e}")
    except subprocess.TimeoutExpired:
        logger.error("Azure CLI command timed out")
        raise RuntimeError("Azure CLI command timed out after 30 seconds")


@tool
async def get_resource(
    resource_id: str,
    runtime: ToolRuntime,
) -> Command:
    """Get detailed information about a specific Azure resource.

    Retrieves the full configuration, properties, and metadata for a resource
    identified by its Azure resource ID.

    Args:
        resource_id: Full Azure resource ID (e.g., '/subscriptions/.../resourceGroups/test/providers/Microsoft.Storage/storageAccounts/myaccount')
        runtime: Tool runtime context (injected automatically)

    Returns:
        Command with updated state (selected_resource) and ToolMessage

    Examples:
        >>> # Get storage account details
        >>> result = await get_resource("/subscriptions/.../storageAccounts/myaccount")

        >>> # Get VM details
        >>> result = await get_resource("/subscriptions/.../virtualMachines/myvm")
    """
    logger.info(f"Getting resource details for: {resource_id}")

    # Build Azure CLI command
    cmd = ["az", "resource", "show", "--ids", resource_id, "-o", "json"]

    try:
        logger.debug(f"Executing command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)

        resource = json.loads(result.stdout)
        logger.info(f"Retrieved resource: {resource.get('name', 'unknown')}")

        # Return Command with state updates and ToolMessage
        resource_name = resource.get("name", "unknown")
        resource_type = resource.get("type", "unknown")
        return Command(
            update={
                "selected_resource": resource,
                "messages": [
                    ToolMessage(
                        content=f"Retrieved resource '{resource_name}' of type {resource_type}",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip()
        if "ResourceNotFound" in error_msg or "NotFound" in error_msg:
            logger.warning(f"Resource not found: {resource_id}")
            raise ValueError(f"Resource not found: {resource_id}")
        else:
            logger.error(f"Failed to get resource: {error_msg}")
            raise RuntimeError(f"Failed to get resource: {error_msg}")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Azure CLI output: {e}")
        raise RuntimeError(f"Failed to parse Azure CLI output: {e}")
    except subprocess.TimeoutExpired:
        logger.error("Azure CLI command timed out")
        raise RuntimeError("Azure CLI command timed out after 30 seconds")


@tool
async def delete_resource(
    resource_id: str,
    runtime: ToolRuntime,
) -> Command:
    """Delete an Azure resource.

    ⚠️ DESTRUCTIVE OPERATION - Requires HITL approval.

    Permanently deletes an Azure resource identified by its resource ID.
    This operation cannot be undone and will trigger human approval.

    Args:
        resource_id: Full Azure resource ID to delete
        runtime: Tool runtime context (injected automatically)

    Returns:
        Command with ToolMessage containing deletion status

    Examples:
        >>> # Delete storage account (will prompt for approval)
        >>> result = await delete_resource("/subscriptions/.../storageAccounts/oldaccount")
    """
    logger.warning(f"Deleting resource: {resource_id}")

    # Build Azure CLI command
    cmd = ["az", "resource", "delete", "--ids", resource_id, "--verbose"]

    try:
        logger.debug(f"Executing command: {' '.join(cmd)}")
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)

        logger.info(f"Successfully deleted resource: {resource_id}")

        # Return Command with ToolMessage
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Resource successfully deleted: {resource_id}",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip()
        if "ResourceNotFound" in error_msg or "NotFound" in error_msg:
            logger.warning(f"Resource not found (may already be deleted): {resource_id}")
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"Resource not found (alrady deleted?): {resource_id}",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )
        else:
            logger.error(f"Failed to delete resource: {error_msg}")
            raise RuntimeError(f"Failed to delete resource: {error_msg}")
    except subprocess.TimeoutExpired:
        logger.error("Azure CLI command timed out")
        raise RuntimeError(
            "Azure CLI command timed out after 120 seconds. Resource may still be deleting."
        )


@tool
async def update_resource_tags(
    resource_id: str,
    tags: dict[str, str],
    runtime: ToolRuntime,
    merge: bool = True,
) -> Command:
    """Update tags on an Azure resource.

    Updates or replaces tags on an existing Azure resource. By default, merges
    new tags with existing ones. Set merge=False to replace all tags.

    Args:
        resource_id: Full Azure resource ID (e.g., /subscriptions/.../resourceGroups/rg/providers/...)
        tags: Dictionary of tag key-value pairs to apply
        runtime: Tool runtime context (injected automatically)
        merge: If True, merge with existing tags. If False, replace all tags (default: True)

    Returns:
        Command with ToolMessage containing updated resource tags

    Examples:
        >>> # Add/update tags (merge mode)
        >>> result = await update_resource_tags(
        ...     "/subscriptions/.../storageAccounts/myaccount",
        ...     {"environment": "production", "cost-center": "engineering"}
        ... )

        >>> # Replace all tags
        >>> result = await update_resource_tags(
        ...     "/subscriptions/.../storageAccounts/myaccount",
        ...     {"owner": "team-a"},
        ...     merge=False
        ... )
    """
    logger.info(f"Updating tags on resource: {resource_id} (merge={merge})")

    # Convert tags dict to Azure CLI format: key1=value1 key2=value2
    tags_str = " ".join([f"{k}={v}" for k, v in tags.items()])

    # Build Azure CLI command
    if merge:
        # Update (merge) tags
        cmd = ["az", "resource", "tag", "--ids", resource_id, "--tags", *tags_str.split()]
    else:
        # Replace all tags
        cmd = [
            "az",
            "resource",
            "update",
            "--ids",
            resource_id,
            "--set",
            f"tags={json.dumps(tags)}",
        ]

    try:
        logger.debug(f"Executing command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)

        # Parse the updated resource
        resource_data = json.loads(result.stdout)
        updated_tags = resource_data.get("tags", {})

        logger.info(f"Successfully updated tags on resource: {resource_id}")

        # Return Command with ToolMessage
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps(
                            {
                                "status": "success",
                                "resource_id": resource_id,
                                "updated_tags": updated_tags,
                                "merge_mode": merge,
                            }
                        ),
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip()
        if "ResourceNotFound" in error_msg or "NotFound" in error_msg:
            logger.error(f"Resource not found: {resource_id}")
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"Resource not found: {resource_id}",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )
        else:
            logger.error(f"Failed to update resource tags: {error_msg}")
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"Failed to update resource tags: {error_msg}",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Azure CLI output: {e}")
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Failed to parse Azure CLI output: {str(e)}",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )
    except subprocess.TimeoutExpired:
        logger.error("Azure CLI command timed out")
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="Azure CLI command timed out after 60 seconds",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )
