"""Validation middleware for Azure permissions and access control.

This middleware provides tools for validating Azure context:
- validate_azure_context: Validates subscription and checks RBAC permissions
- check_resource_group: Checks if resource group exists and validates access

The middleware also preserves Azure context in state after tool execution.
"""

import asyncio
import json
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import Command

from arma.agent.state import ARMAAgentState
from arma.core.logging import get_logger

logger = get_logger(__name__)


class PreflightMiddleware(AgentMiddleware):
    """Middleware to validate Azure permissions and access control.

    Provides tools for Azure validation and preserves context in state.
    """

    state_schema = ARMAAgentState

    def __init__(
        self,
        *,
        validate_rbac_roles: bool = True,
        required_roles: list[str] | None = None,
        timeout_seconds: int = 10,
    ) -> None:
        """Initialize PreflightMiddleware.

        Args:
            validate_rbac_roles: If True, validate user has deployment permissions
            required_roles: List of required role names (defaults to ['Contributor', 'Owner'])
            timeout_seconds: Timeout for Azure CLI commands in seconds
        """
        super().__init__()
        self.validate_rbac_roles = validate_rbac_roles
        self.required_roles = required_roles or ["Contributor", "Owner"]
        self.timeout_seconds = timeout_seconds

        @tool(description="Validate Azure subscription and check RBAC permissions")
        async def validate_azure_context(
            subscription_id: str,
            runtime: ToolRuntime,
        ) -> Command:
            """Validate Azure subscription and check RBAC permissions.

            Args:
                subscription_id: Azure subscription GUID
                runtime: Tool runtime context

            Returns:
                Command with state updates and validation results
            """
            logger.debug(f"Validating subscription: {subscription_id}")

            try:
                # Validate subscription
                process = await asyncio.create_subprocess_exec(
                    "az",
                    "account",
                    "show",
                    "--subscription",
                    subscription_id,
                    "-o",
                    "json",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout_seconds,
                )

                if process.returncode != 0:
                    error_msg = stderr.decode().strip()
                    message = f"Invalid Azure subscription: {subscription_id}\n{error_msg}\nUse 'az account list' to see available subscriptions."
                    return Command(
                        update={
                            "messages": [
                                ToolMessage(content=message, tool_call_id=runtime.tool_call_id)
                            ]
                        }
                    )

                account_info = json.loads(stdout.decode())
                subscription_name = account_info.get("name", "Unknown")
                tenant_id = account_info.get("tenantId", "")

                updates = {
                    "subscription_id": subscription_id,
                    "subscription_name": subscription_name,
                    "tenant_id": tenant_id,
                }

                message_parts = [f"Validated subscription: {subscription_name} ({subscription_id})"]

                # Check RBAC roles if enabled
                if self.validate_rbac_roles:
                    role_conditions = " || ".join(
                        [f"contains(roleDefinitionName, '{role}')" for role in self.required_roles]
                    )
                    perms_process = await asyncio.create_subprocess_exec(
                        "az",
                        "role",
                        "assignment",
                        "list",
                        "--subscription",
                        subscription_id,
                        "--assignee",
                        "@me",
                        "--query",
                        f"[?{role_conditions}].roleDefinitionName",
                        "-o",
                        "json",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    perms_stdout, _ = await asyncio.wait_for(
                        perms_process.communicate(),
                        timeout=self.timeout_seconds,
                    )

                    if perms_process.returncode == 0:
                        roles = json.loads(perms_stdout.decode())
                        if roles:
                            updates["user_roles"] = roles
                            roles_str = ", ".join(roles)
                            message_parts.append(f"Deployment permissions: {roles_str}")
                        else:
                            message_parts.append(
                                f"Warning: No deployment permissions found (required: {', '.join(self.required_roles)})"
                            )

                message = "\n".join(message_parts)
                updates["messages"] = [
                    ToolMessage(content=message, tool_call_id=runtime.tool_call_id)
                ]

                return Command(update=updates)

            except TimeoutError:
                message = f"Subscription validation timed out after {self.timeout_seconds} seconds"
                return Command(
                    update={
                        "messages": [
                            ToolMessage(content=message, tool_call_id=runtime.tool_call_id)
                        ]
                    }
                )
            except Exception as e:
                message = f"Validation error: {str(e)}"
                return Command(
                    update={
                        "messages": [
                            ToolMessage(content=message, tool_call_id=runtime.tool_call_id)
                        ]
                    }
                )

        @tool(description="Check if resource group exists and validate access")
        async def check_resource_group(
            subscription_id: str,
            resource_group: str,
            location: str,
            runtime: ToolRuntime,
        ) -> Command:
            """Check if resource group exists and validate access.

            Args:
                subscription_id: Azure subscription GUID
                resource_group: Resource group name
                location: Azure region (used if creating new resource group)
                runtime: Tool runtime context

            Returns:
                Command with state updates and resource group status
            """
            logger.debug(f"Checking resource group: {resource_group}")

            try:
                # Check if resource group exists
                check_process = await asyncio.create_subprocess_exec(
                    "az",
                    "group",
                    "show",
                    "-n",
                    resource_group,
                    "--subscription",
                    subscription_id,
                    "-o",
                    "json",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                check_stdout, _ = await asyncio.wait_for(
                    check_process.communicate(),
                    timeout=self.timeout_seconds,
                )

                updates: dict[str, Any] = {
                    "resource_group": resource_group,
                    "location": location,
                    "resource_group_checked": True,
                }

                if check_process.returncode == 0:
                    # Resource group exists
                    rg_info = json.loads(check_stdout.decode())
                    actual_location = rg_info.get("location", location)
                    updates["location"] = actual_location
                    updates["resource_group_exists"] = True

                    message_parts = [
                        f"Resource group '{resource_group}' exists in {actual_location}"
                    ]

                    # Check RBAC roles if enabled
                    if self.validate_rbac_roles:
                        role_conditions = " || ".join(
                            [
                                f"contains(roleDefinitionName, '{role}')"
                                for role in self.required_roles
                            ]
                        )
                        perms_process = await asyncio.create_subprocess_exec(
                            "az",
                            "role",
                            "assignment",
                            "list",
                            "--resource-group",
                            resource_group,
                            "--subscription",
                            subscription_id,
                            "--assignee",
                            "@me",
                            "--query",
                            f"[?{role_conditions}].roleDefinitionName",
                            "-o",
                            "json",
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        perms_stdout, _ = await asyncio.wait_for(
                            perms_process.communicate(),
                            timeout=self.timeout_seconds,
                        )

                        if perms_process.returncode == 0:
                            roles = json.loads(perms_stdout.decode())
                            if roles:
                                updates["resource_group_accessible"] = True
                                roles_str = ", ".join(roles)
                                message_parts.append(f"Access permissions: {roles_str}")
                            else:
                                updates["resource_group_accessible"] = False
                                message_parts.append("Warning: No deployment permissions found")

                    if "tags" in rg_info and rg_info["tags"]:
                        updates["tags"] = rg_info["tags"]

                    message = "\n".join(message_parts)
                else:
                    # Resource group doesn't exist
                    updates["resource_group_exists"] = False
                    updates["resource_group_accessible"] = True
                    message = f"Resource group '{resource_group}' does not exist. It will be created in {location}."

                updates["messages"] = [
                    ToolMessage(content=message, tool_call_id=runtime.tool_call_id)
                ]
                return Command(update=updates)

            except TimeoutError:
                message = f"Resource group check timed out after {self.timeout_seconds} seconds"
                return Command(
                    update={
                        "messages": [
                            ToolMessage(content=message, tool_call_id=runtime.tool_call_id)
                        ]
                    }
                )
            except Exception as e:
                message = f"Error checking resource group: {str(e)}"
                return Command(
                    update={
                        "messages": [
                            ToolMessage(content=message, tool_call_id=runtime.tool_call_id)
                        ]
                    }
                )

        self.tools = [validate_azure_context, check_resource_group]

    @property
    def name(self) -> str:
        """Return the middleware name identifier."""
        return "validation"

    def after_tool(
        self, state: AgentState, runtime: Runtime
    ) -> dict[str, Any] | None:  # noqa: ARG002
        """Preserve Azure context in state after tool execution.

        Args:
            state: Current agent state
            runtime: Runtime context

        Returns:
            Dictionary with state updates to preserve context, None if no updates needed
        """
        updates = {}

        # Preserve subscription context
        subscription_id = state.get("subscription_id")
        if subscription_id:
            updates["subscription_id"] = subscription_id
            logger.debug(f"Preserving subscription_id: {subscription_id}")

        subscription_name = state.get("subscription_name")
        if subscription_name:
            updates["subscription_name"] = subscription_name

        tenant_id = state.get("tenant_id")
        if tenant_id:
            updates["tenant_id"] = tenant_id

        # Preserve resource group context
        resource_group = state.get("resource_group")
        if resource_group:
            updates["resource_group"] = resource_group
            logger.debug(f"Preserving resource_group: {resource_group}")

        location = state.get("location")
        if location:
            updates["location"] = location

        # Preserve validation flags
        if state.get("resource_group_checked"):
            updates["resource_group_checked"] = True

        if state.get("resource_group_exists") is not None:
            updates["resource_group_exists"] = state.get("resource_group_exists")

        if state.get("resource_group_accessible") is not None:
            updates["resource_group_accessible"] = state.get("resource_group_accessible")

        # Preserve roles
        user_roles = state.get("user_roles")
        if user_roles:
            updates["user_roles"] = user_roles

        if updates:
            logger.debug(f"Preserving context: {list(updates.keys())}")
            return updates

        return None
