"""Tagging middleware for automatically tagging deployed resources."""

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime

from langchain.agents.middleware.types import AgentMiddleware
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from arma.agent.state import ARMAAgentState
from arma.core.logging import get_logger

logger = get_logger(__name__)


class TaggingMiddleware(AgentMiddleware):
    """Middleware to automatically tag deployed Azure resources.

    Tags resources after successful execute_deployment with:
    - deployer: User who initiated the deployment
    - deployed_by: Agent identifier
    - deployed_at: ISO 8601 timestamp

    Example:
        >>> TaggingMiddleware(
        ...     user_id_key="user_id",
        ...     agent_name="arma-agent",
        ...     mode="best-effort"
        ... )
    """

    state_schema = ARMAAgentState

    def __init__(
        self,
        user_id_key: str = "user_id",
        agent_name: str = "arma-agent",
        mode: str = "best-effort",
        enabled: bool = True,
    ):
        """Initialize tagging middleware.

        Args:
            user_id_key: State key for user identifier
            agent_name: Agent deploying resources
            mode: Error handling - "best-effort" or "strict"
            enabled: Whether tagging is enabled
        """
        super().__init__()
        self.user_id_key = user_id_key
        self.agent_name = agent_name
        self.mode = mode
        self.enabled = enabled

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable,
    ) -> ToolMessage | Command:
        """Tag resources after successful execute_deployment."""
        tool_name = request.tool_call.get("name", "")
        result = await handler(request)

        if not self.enabled or tool_name != "execute_deployment":
            return result

        state = request.state

        try:
            if isinstance(result, Command):
                if result.update is None:
                    return result
                messages = result.update.get("messages", [])
                if not messages or not isinstance(messages[0], ToolMessage):
                    return result
                result_content = messages[0].content
            elif isinstance(result, ToolMessage):
                result_content = result.content
            else:
                return result

            if isinstance(result_content, str):
                try:
                    result_dict = json.loads(result_content)
                except json.JSONDecodeError:
                    return result
            elif isinstance(result_content, dict):
                result_dict = result_content
            else:
                return result
        except Exception as e:
            logger.warning(f"Could not parse tool result: {e}")
            return result

        status = result_dict.get("status")
        if status not in ("completed", "success"):
            return result

        resources_created = result_dict.get("resources_created", [])
        if not resources_created:
            return result

        user_id = state.get(self.user_id_key, "unknown")
        tagging_results = await self._tag_resources(resources_created, user_id)

        deployment_name = result_dict.get("deployment_id", "deployment")
        duration = result_dict.get("duration_seconds", 0)

        friendly_message = f"Deployment {deployment_name} completed in {duration:.2f}s"

        if tagging_results["successful_tags"] > 0:
            friendly_message += f"\nTagged {tagging_results['successful_tags']} resource(s)"

        if tagging_results["failed_tags"] > 0:
            friendly_message += (
                f"\nWarning: Failed to tag {tagging_results['failed_tags']} resource(s)"
            )

        if isinstance(result, Command):
            if result.update is None:
                return result
            messages = result.update.get("messages", [])

            if messages and isinstance(messages[0], ToolMessage):
                tool_message = ToolMessage(
                    content=friendly_message,
                    tool_call_id=messages[0].tool_call_id,
                )
            else:
                return result

            return Command(
                update={
                    **(result.update or {}),
                    "tagging_results": tagging_results,
                    "messages": [tool_message],
                }
            )

        elif isinstance(result, ToolMessage):
            tool_message = ToolMessage(
                content=friendly_message,
                tool_call_id=result.tool_call_id,
            )

            return Command(
                update={
                    "tagging_results": tagging_results,
                    "messages": [tool_message],
                }
            )

        return result

    async def _tag_resources(self, resources: list[dict], user_id: str) -> dict:
        """Tag a list of Azure resources.

        Args:
            resources: List of resource dicts with 'id', 'name', 'type'
            user_id: User identifier for deployer tag

        Returns:
            Dictionary with tagging results and metadata
        """
        timestamp = datetime.now(UTC).isoformat()

        # Prepare tags
        tags = {
            "deployer": user_id,
            "deployed_by": self.agent_name,
            "deployed_at": timestamp,
        }

        tagged_resources = []
        failed_resources = []

        for resource in resources:
            resource_id = resource.get("id")
            if not resource_id:
                logger.warning("Skipping resource with no ID")
                continue

            try:
                await self._tag_resource(resource_id, tags)
                tagged_resources.append(
                    {
                        "id": resource_id,
                        "name": resource.get("name"),
                        "type": resource.get("type"),
                        "tags": tags,
                    }
                )

            except Exception as e:
                error_msg = str(e)
                failed_resources.append(
                    {
                        "id": resource_id,
                        "name": resource.get("name"),
                        "type": resource.get("type"),
                        "error": error_msg,
                    }
                )

                if self.mode == "strict":
                    logger.error(f"Failed to tag resource {resource_id}: {error_msg}")
                    raise
                else:
                    logger.warning(
                        f"Failed to tag {resource.get('name')} ({resource.get('type')}): {error_msg}"
                    )

        return {
            "tagged_resources": tagged_resources,
            "failed_resources": failed_resources,
            "tags_applied": tags,
            "timestamp": timestamp,
            "total_resources": len(resources),
            "successful_tags": len(tagged_resources),
            "failed_tags": len(failed_resources),
        }

    async def _tag_resource(self, resource_id: str, tags: dict[str, str]) -> None:
        """Tag a single Azure resource using Azure CLI.

        Args:
            resource_id: Full Azure resource ID
            tags: Dictionary of tag key-value pairs

        Raises:
            RuntimeError: If tagging command fails
        """
        tag_args = [f"{key}={value}" for key, value in tags.items()]

        cmd = [
            "az",
            "resource",
            "tag",
            "--ids",
            resource_id,
            "--tags",
            *tag_args,
            "-o",
            "json",
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

            if process.returncode != 0:
                error_detail = stderr.decode().strip() if stderr else "Unknown error"
                raise RuntimeError(
                    f"Tagging failed (exit code {process.returncode}): {error_detail}"
                )

        except TimeoutError:
            raise RuntimeError("Tagging command timed out after 30 seconds")
