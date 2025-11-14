"""Query tools for Azure resource operations.

This module provides tools for listing, getting, deleting, and managing Azure resources.
"""

import json
import subprocess
from typing import Any

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from arma.core.logging import get_logger

logger = get_logger(__name__)


@tool(description="Check if a resource exists in Azure")
async def check_existing_resource(
    subscription_id: str,
    resource_group: str,
    resource_name: str,
    resource_type: str,
    runtime: ToolRuntime,
) -> Command:
    """Check if a resource already exists in Azure.

    Args:
        subscription_id: Azure subscription ID.
        resource_group: Name of the Azure resource group.
        resource_name: Name of the Azure resource to check.
        resource_type: Azure resource type (e.g., 'Microsoft.Storage/storageAccounts').
        runtime: Tool runtime context (injected automatically).

    Returns:
        Command with state updates and tool message.
    """
    logger.debug(f"Checking resource: {resource_name} ({resource_type})")

    try:
        # Build resource ID
        resource_id = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/{resource_type}/{resource_name}"
        logger.debug(f"Checking resource ID: {resource_id}")

        # Check resource existence using Azure CLI
        cmd = ["az", "resource", "show", "--ids", resource_id, "-o", "json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        updates: dict[str, Any] = {}

        if result.returncode == 0:
            # Resource exists
            resource_details = json.loads(result.stdout)
            updates["intent"] = "update"
            logger.debug(f"Resource exists: {resource_name} - updating intent")

            message = f"Resource '{resource_name}' exists. Will update existing resource. Details {json.dumps(resource_details, indent=2)}"
        else:
            # Resource doesn't exist
            error_msg = result.stderr.lower()
            if "could not be found" in error_msg or "notfound" in error_msg:
                logger.debug(f"Resource does not exist: {resource_name}")
                message = f"Resource '{resource_name}' does not exist. Will create new resource."
            else:
                logger.error(f"Error checking resource existence: {result.stderr}")
                message = f"Unable to verify if resource exists: {result.stderr[:200]}"

        updates["messages"] = [ToolMessage(content=message, tool_call_id=runtime.tool_call_id)]
        return Command(update=updates)

    except subprocess.TimeoutExpired:
        logger.error(f"Timeout checking resource existence: {resource_name}")
        message = "Timeout checking resource existence"
        return Command(
            update={"messages": [ToolMessage(content=message, tool_call_id=runtime.tool_call_id)]}
        )
    except Exception as e:
        logger.error(f"Error checking resource: {e}")
        message = f"Error checking resource: {str(e)}"
        return Command(
            update={"messages": [ToolMessage(content=message, tool_call_id=runtime.tool_call_id)]}
        )


@tool(description="Create a resource group if it doesn't exist")
async def create_resource_group(
    subscription_id: str,
    resource_group: str,
    location: str,
    runtime: ToolRuntime,
) -> Command:
    """Create a resource group if it doesn't already exist.

    Args:
        subscription_id: Azure subscription ID.
        resource_group: Name of the resource group.
        location: Azure region (e.g., 'eastus').
        runtime: Tool runtime context (injected automatically).

    Returns:
        Command with state updates and tool message.
    """
    try:
        # Check if RG exists
        check_cmd = [
            "az",
            "group",
            "show",
            "-n",
            resource_group,
            "--subscription",
            subscription_id,
            "-o",
            "json",
        ]
        check_result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=10)

        updates: dict[str, Any] = {
            "subscription_id": subscription_id,  # Preserve subscription_id
            "resource_group": resource_group,
            "location": location,
            "resource_group_checked": True,
        }

        if check_result.returncode == 0:
            # Resource group exists - extract details
            rg_info = json.loads(check_result.stdout)
            updates["location"] = rg_info.get("location", location)
            if "tags" in rg_info and rg_info["tags"]:
                updates["tags"] = rg_info["tags"]

            logger.debug(f"Resource group exists: {resource_group} in {updates['location']}")
            message = f"Resource group '{resource_group}' already exists in {updates['location']}"
        else:
            # Create RG
            logger.debug(f"Creating resource group: {resource_group}")
            create_cmd = [
                "az",
                "group",
                "create",
                "-n",
                resource_group,
                "-l",
                location,
                "--subscription",
                subscription_id,
                "-o",
                "json",
            ]
            create_result = subprocess.run(create_cmd, capture_output=True, text=True, timeout=30)

            if create_result.returncode == 0:
                # Extract created RG details
                rg_info = json.loads(create_result.stdout)
                updates["location"] = rg_info.get("location", location)

                logger.debug(f"Resource group created: {resource_group} in {updates['location']}")
                message = f"Created resource group '{resource_group}' in {updates['location']}"
            else:
                logger.error(f"Failed to create resource group: {create_result.stderr}")
                message = f"Failed to create resource group: {create_result.stderr[:200]}"

        updates["messages"] = [ToolMessage(content=message, tool_call_id=runtime.tool_call_id)]
        return Command(update=updates)

    except subprocess.TimeoutExpired:
        logger.error("Timeout creating resource group")
        message = "Timeout creating resource group"
        return Command(
            update={"messages": [ToolMessage(content=message, tool_call_id=runtime.tool_call_id)]}
        )
    except Exception as e:
        logger.error(f"Error creating resource group: {e}")
        message = f"Error creating resource group: {str(e)}"
        return Command(
            update={"messages": [ToolMessage(content=message, tool_call_id=runtime.tool_call_id)]}
        )


@tool
async def list_resources(
    subscription_id: str,
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
        subscription_id: Azure subscription ID
        resource_type: Azure resource type (e.g., 'Microsoft.Storage/storageAccounts')
        runtime: Tool runtime context (injected automatically)
        location: Filter by Azure region (e.g., 'eastus', 'westus2')
        resource_group: Filter by resource group name
        tags: Filter by tags in format 'key1=value1 key2=value2'

    Returns:
        Command with updated state (query_results, last_query) and ToolMessage

    Examples:
        >>> # List all resources
        >>> result = await list_resources(subscription_id="your-subscription-id")

        >>> # List all resources in rg test-rg-01
        >>> result = await list_resources(subscription_id="your-subscription-id", resource_group="test-rg-01")

        >>> # List all storage accounts in subscription
        >>> result = await list_resources(subscription_id="your-subscription-id", resource_type="Microsoft.Storage/storageAccounts")

        >>> # List VMs in specific location
        >>> result = await list_resources(subscription_id="your-subscription-id", resource_type="Microsoft.Compute/virtualMachines", location="eastus")

        >>> # List resources in specific resource group
        >>> result = await list_resources(subscription_id="your-subscription-id", resource_group="prod-rg")
    """
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
        logger.debug(f"Found {len(resources)} resources")

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
    logger.debug(f"Getting resource: {resource_id}")

    # Build Azure CLI command
    cmd = ["az", "resource", "show", "--ids", resource_id, "-o", "json"]

    try:
        logger.debug(f"Executing command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)

        resource = json.loads(result.stdout)
        logger.debug(f"Retrieved resource: {resource.get('name')}")

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
    logger.debug(f"Deleting resource: {resource_id}")

    # Build Azure CLI command
    cmd = ["az", "resource", "delete", "--ids", resource_id, "--verbose"]

    try:
        logger.debug(f"Executing command: {' '.join(cmd)}")
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)

        logger.debug(f"Deleted resource: {resource_id}")

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
            logger.debug(f"Resource not found (may already be deleted): {resource_id}")
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"Resource not found (already deleted?): {resource_id}",
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
    logger.debug(f"Updating tags: {resource_id} (merge={merge})")

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

        logger.debug(f"Tags updated: {resource_id}")

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
