"""Validation middleware for Azure context extraction and validation.

This middleware automatically:
1. Extracts Azure subscription ID from user messages
2. Validates the subscription using Azure CLI
3. Updates the graph state with validated context
4. Extracts resource group and location information
5. Provides check_existing_resource and create_resource_group tools

This replaces the tool-based validation approach to ensure state updates
properly propagate through the graph.
"""

import json
import re
import subprocess
from typing import Any, NotRequired

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import Command

from arma.core.logging import get_logger

logger = get_logger(__name__)

# Regex pattern for Azure subscription GUID
GUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


class ValidationState(AgentState):
    """Extended state for validation middleware."""

    resource_group_checked: NotRequired[bool]
    """Whether resource group existence has been checked."""


class PreflightMiddleware(AgentMiddleware):
    """Middleware to extract and validate Azure context from messages.

    This middleware uses the before_agent hook to process incoming messages
    and extract Azure context (subscription_id, resource_group, location)
    before the agent starts processing.

    Also provides validation tools that work with the middleware state.
    """

    state_schema = ValidationState

    def __init__(self) -> None:
        """Initialize ValidationMiddleware with tools."""
        super().__init__()

        @tool(description="Check if a resource exists in Azure")
        async def check_existing_resource(
            resource_name: str,
            resource_type: str,
            runtime: ToolRuntime,
        ) -> Command:
            """Check if a resource already exists in Azure.

            Args:
                resource_name: Name of the Azure resource to check.
                resource_type: Azure resource type (e.g., 'Microsoft.Storage/storageAccounts').
                runtime: Tool runtime context (injected automatically).

            Returns:
                Command with state updates and tool message.
            """
            logger.info(f"Checking existence of resource: {resource_name} (type: {resource_type})")

            # Get context from state
            subscription_id = runtime.state.get("subscription_id")
            resource_group = runtime.state.get("resource_group")

            # Validate we have required context
            if not subscription_id:
                logger.warning("Cannot check resource existence: subscription_id not in state")
                message = (
                    "⚠️ Cannot check existence: subscription_id required. "
                    "Please ask the user to provide the subscription Id"
                )
                return Command(
                    update={
                        "messages": [
                            ToolMessage(content=message, tool_call_id=runtime.tool_call_id)
                        ]
                    }
                )

            if not resource_group:
                logger.warning("Cannot check resource existence: resource_group not in state")
                message = (
                    "⚠️ Resource group not set. Please use the create_resource_group tool first to "
                    "specify or create a resource group, then retry checking the resource."
                )
                return Command(
                    update={
                        "messages": [
                            ToolMessage(content=message, tool_call_id=runtime.tool_call_id)
                        ]
                    }
                )

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
                    logger.info(f"Resource EXISTS: {resource_name} - Intent changed to 'update'")

                    message = f"Resource '{resource_name}' exists. Will update existing resource. Details {json.dumps(resource_details, indent=2)}"
                else:
                    # Resource doesn't exist
                    error_msg = result.stderr.lower()
                    if "could not be found" in error_msg or "notfound" in error_msg:
                        logger.info(
                            f"Resource DOES NOT exist: {resource_name} - Intent remains 'deploy'"
                        )
                        message = (
                            f"Resource '{resource_name}' does not exist. Will create new resource."
                        )
                    else:
                        logger.error(f"Error checking resource existence: {result.stderr}")
                        message = f"Unable to verify if resource exists: {result.stderr[:200]}"

                updates["messages"] = [
                    ToolMessage(content=message, tool_call_id=runtime.tool_call_id)
                ]
                return Command(update=updates)

            except subprocess.TimeoutExpired:
                logger.error(f"Timeout checking resource existence: {resource_name}")
                message = "Timeout checking resource existence"
                return Command(
                    update={
                        "messages": [
                            ToolMessage(content=message, tool_call_id=runtime.tool_call_id)
                        ]
                    }
                )
            except Exception as e:
                logger.error(f"Error checking resource: {e}")
                message = f"Error checking resource: {str(e)}"
                return Command(
                    update={
                        "messages": [
                            ToolMessage(content=message, tool_call_id=runtime.tool_call_id)
                        ]
                    }
                )

        @tool(description="Create a resource group if it doesn't exist")
        async def create_resource_group(
            resource_group_name: str,
            location: str,
            runtime: ToolRuntime,
        ) -> Command:
            """Create a resource group if it doesn't already exist.

            Args:
                resource_group_name: Name of the resource group.
                location: Azure region (e.g., 'eastus').
                runtime: Tool runtime context (injected automatically).

            Returns:
                Command with state updates and tool message.
            """
            logger.info(f"Creating/checking resource group: {resource_group_name} in {location}")

            subscription_id = runtime.state.get("subscription_id")
            if not subscription_id:
                logger.warning("Cannot create resource group: subscription_id not in state")
                message = "Cannot create resource group: subscription_id required"
                return Command(
                    update={
                        "messages": [
                            ToolMessage(content=message, tool_call_id=runtime.tool_call_id)
                        ]
                    }
                )

            try:
                # Check if RG exists
                check_cmd = [
                    "az",
                    "group",
                    "show",
                    "-n",
                    resource_group_name,
                    "--subscription",
                    subscription_id,
                    "-o",
                    "json",
                ]
                check_result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=10)

                updates: dict[str, Any] = {
                    "subscription_id": subscription_id,  # Preserve subscription_id
                    "resource_group": resource_group_name,
                    "location": location,
                    "resource_group_checked": True,
                }

                if check_result.returncode == 0:
                    # Resource group exists - extract details
                    rg_info = json.loads(check_result.stdout)
                    updates["location"] = rg_info.get("location", location)
                    if "tags" in rg_info and rg_info["tags"]:
                        updates["tags"] = rg_info["tags"]

                    logger.info(
                        f"Resource group already exists: {resource_group_name} "
                        f"(location: {updates['location']})"
                    )
                    message = f"Resource group '{resource_group_name}' already exists in {updates['location']}"
                else:
                    # Create RG
                    logger.info(f"Creating resource group: {resource_group_name}")
                    create_cmd = [
                        "az",
                        "group",
                        "create",
                        "-n",
                        resource_group_name,
                        "-l",
                        location,
                        "--subscription",
                        subscription_id,
                        "-o",
                        "json",
                    ]
                    create_result = subprocess.run(
                        create_cmd, capture_output=True, text=True, timeout=30
                    )

                    if create_result.returncode == 0:
                        # Extract created RG details
                        rg_info = json.loads(create_result.stdout)
                        updates["location"] = rg_info.get("location", location)

                        logger.info(
                            f"Resource group created: {resource_group_name} "
                            f"(location: {updates['location']})"
                        )
                        message = f"Created resource group '{resource_group_name}' in {updates['location']}"
                    else:
                        logger.error(f"Failed to create resource group: {create_result.stderr}")
                        message = f"Failed to create resource group: {create_result.stderr[:200]}"

                updates["messages"] = [
                    ToolMessage(content=message, tool_call_id=runtime.tool_call_id)
                ]
                return Command(update=updates)

            except subprocess.TimeoutExpired:
                logger.error("Timeout creating resource group")
                message = "Timeout creating resource group"
                return Command(
                    update={
                        "messages": [
                            ToolMessage(content=message, tool_call_id=runtime.tool_call_id)
                        ]
                    }
                )
            except Exception as e:
                logger.error(f"Error creating resource group: {e}")
                message = f"Error creating resource group: {str(e)}"
                return Command(
                    update={
                        "messages": [
                            ToolMessage(content=message, tool_call_id=runtime.tool_call_id)
                        ]
                    }
                )

        self.tools = [check_existing_resource, create_resource_group]

    @property
    def name(self) -> str:
        """Return the middleware name identifier."""
        return "validation"

    def after_tool(
        self, state: AgentState, runtime: Runtime
    ) -> dict[str, Any] | None:  # noqa: ARG002
        """Ensure Azure context is preserved in state after tool execution.

        This hook ensures that subscription_id, resource_group, and location
        are always available in state for subsequent tool calls.

        Args:
            state: Current agent state
            runtime: Runtime context (unused)

        Returns:
            Dictionary with state updates to preserve context, None if no updates needed
        """
        # Check if we need to preserve any context
        updates = {}

        # If subscription_id was set but might be lost, preserve it
        subscription_id = state.get("subscription_id")
        if subscription_id:
            updates["subscription_id"] = subscription_id
            logger.debug(
                f"Preserving subscription_id in state: {subscription_id} (type: {type(subscription_id).__name__})"
            )
        else:
            logger.warning(
                f"after_tool: subscription_id is empty/None in state! State keys: {list(state.keys())[:15]}"
            )

        # Preserve resource_group if set
        resource_group = state.get("resource_group")
        if resource_group:
            updates["resource_group"] = resource_group
            logger.debug(f"Preserving resource_group in state: {resource_group}")

        # Preserve location if set
        location = state.get("location")
        if location:
            updates["location"] = location
            logger.debug(f"Preserving location in state: {location}")

        # Return updates if any context needs to be preserved
        if updates:
            logger.info(
                f"After tool: preserving Azure context - {list(updates.keys())} with values: {updates}"
            )
            return updates

        logger.warning("After tool: No Azure context to preserve!")
        return None

    def before_agent(
        self, state: AgentState, runtime: Runtime
    ) -> dict[str, Any] | None:  # noqa: ARG002
        """Process messages to extract and validate Azure context.

        This runs once at the start of each agent invocation to extract
        Azure context from the user's message.

        Args:
            state: Current agent state
            runtime: Runtime context (unused)

        Returns:
            Dictionary with state updates if context was extracted, None otherwise
        """
        logger.debug("Processing messages")

        # Get the last user message
        messages = state.get("messages", [])
        if not messages or not isinstance(messages, list):
            logger.debug("No messages to process")
            return None

        last_message = None
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "human":
                last_message = msg
                break

        if not last_message:
            logger.debug("No human message found")
            return None

        # Get message content
        content = ""
        if hasattr(last_message, "content"):
            if isinstance(last_message.content, str):
                content = last_message.content
            elif isinstance(last_message.content, list):
                # Handle complex content structure
                for item in last_message.content:
                    if isinstance(item, dict) and "text" in item:
                        content += item["text"] + " "
                    elif isinstance(item, str):
                        content += item + " "

        if not content:
            logger.debug("No content to process")
            return None

        logger.debug(f"Processing content: {content[:100]}...")

        updates = {}

        # Extract subscription ID if not already in state
        current_sub = state.get("subscription_id")
        logger.debug(
            f"before_agent: current subscription_id in state: '{current_sub}' (type: {type(current_sub).__name__ if current_sub else 'None'})"
        )

        if not current_sub:
            # Look for subscription ID in message
            match = GUID_PATTERN.search(content)
            if match:
                subscription_id = match.group(0)
                logger.debug(f"Found subscription ID in message: {subscription_id}")

                # Validate the subscription and get context
                context = self._validate_subscription(subscription_id)
                if context:
                    # Update with full Azure context
                    updates.update(context)
                    logger.info(
                        f"Updated Azure context: subscription_id={context['subscription_id']}, "
                        f"subscription={context['subscription_name']}, "
                        f"tenant={context['tenant_id']}"
                    )
                else:
                    logger.warning(f"Subscription {subscription_id} validation failed")
        else:
            logger.debug(f"Subscription ID already in state: {current_sub}")

        # Extract resource group if mentioned explicitly (fallback for simple cases)
        content_lower = content.lower()
        current_rg = state.get("resource_group")

        # Basic extraction as fallback - prompt should handle complex cases
        if not current_rg:
            rg_match = re.search(
                r"(?:resource\s+group|rg)\s+['\"]?(\w+[-\w]*)['\"]?", content_lower
            )
            if rg_match:
                resource_group = rg_match.group(1)
                updates["resource_group"] = resource_group
                logger.info(f"Extracted resource_group: {resource_group}")

        # Extract location if mentioned explicitly (fallback for simple cases)
        current_location = state.get("location")
        if not current_location:
            # Most common Azure locations only
            locations = ["eastus", "eastus2", "westus", "westus2", "centralus"]
            for location in locations:
                if location in content_lower:
                    updates["location"] = location
                    logger.info(f"Extracted location: {location}")
                    break

        # Return updates if we found any
        if updates:
            logger.info(f"Applying updates: {updates}")
            return updates

        return None

    def _validate_subscription(self, subscription_id: str) -> dict[str, str] | None:
        """Validate subscription ID and extract Azure context using Azure CLI.

        Args:
            subscription_id: Azure subscription GUID to validate

        Returns:
            Dictionary with Azure context (subscription_name, tenant_id, etc.) if valid, None otherwise
        """
        try:
            result = subprocess.run(
                ["az", "account", "show", "--subscription", subscription_id, "-o", "json"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                account_info = json.loads(result.stdout)

                context = {
                    "subscription_id": subscription_id,
                    "subscription_name": account_info.get("name", ""),
                    "tenant_id": account_info.get("tenantId", ""),
                }

                logger.info(
                    f"Subscription {subscription_id} is VALID "
                    f"(name: {context['subscription_name']}, tenant: {context['tenant_id']})"
                )
                return context
            else:
                logger.warning(f"Subscription {subscription_id} validation failed: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            logger.error("Subscription validation timed out")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Azure CLI output: {e}")
            return None
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return None
