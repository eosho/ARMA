"""Tagging middleware for automatically tagging deployed resources."""

import logging
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime

from langchain.agents.middleware.types import AgentMiddleware
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        user_id_key: str = "user_id",
        agent_name: str = "arma-agent",
        mode: str = "best-effort",
        enabled: bool = True,
    ):
        """Initialize tagging middleware.

        Args:
            user_id_key: State key to read user identifier from
            agent_name: Name of the agent deploying resources
            mode: Error handling mode - "best-effort" (log warnings) or "strict" (fail on error)
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
        """Async version - tag resources after successful execute_deployment.

        See wrap_tool_call for full documentation.
        """
        # Get tool name
        tool_name = request.tool_call.get("name", "")

        # Execute the tool
        result = await handler(request)

        logger.debug(f"TaggingMiddleware.awrap_tool_call: tool_name='{tool_name}'")

        # Skip if tagging is disabled
        if not self.enabled:
            logger.info("Tagging is disabled")
            return result

        # Only tag after execute_deployment
        if tool_name != "execute_deployment":
            logger.debug(f"Skipping tagging - tool is '{tool_name}', not 'execute_deployment'")
            return result

        logger.debug("execute_deployment detected, checking result status")

        # Get state
        state = request.state

        # Parse result from Command or ToolMessage
        import json

        try:
            # Handle Command type (from execute_deployment)
            if isinstance(result, Command):
                logger.debug("Result is Command, extracting ToolMessage from update")
                # Get the ToolMessage from Command.update['messages']
                if result.update is not None:
                    messages = result.update.get("messages", [])
                    if messages and isinstance(messages[0], ToolMessage):
                        result_content = messages[0].content
                    else:
                        logger.debug("Skipping tagging - no ToolMessage in Command")
                        return result
                else:
                    logger.debug("Skipping tagging - Command.update is None")
                    return result
            # Handle ToolMessage type
            elif isinstance(result, ToolMessage):
                result_content = result.content
            else:
                logger.debug(f"Skipping tagging - unexpected result type: {type(result)}")
                return result

            # Parse the content
            if isinstance(result_content, str):
                try:
                    result_dict = json.loads(result_content)
                except json.JSONDecodeError:
                    logger.debug("Skipping tagging - could not parse JSON content")
                    result_dict = {}
            elif isinstance(result_content, dict):
                result_dict = result_content
            else:
                logger.debug("Skipping tagging - could not parse result")
                return result
        except Exception as e:
            logger.warning(f"Could not parse tool result: {e}")
            return result

        status = result_dict.get("status")
        logger.info(f"Deployment status: '{status}'")

        if status not in ("completed", "success"):
            logger.debug(
                f"Skipping tagging - deployment status is '{status}', not 'completed' or 'success'"
            )
            return result

        # Extract resources to tag
        resources_created = result_dict.get("resources_created", [])
        if not resources_created:
            logger.info("Skipping tagging - no resources created")
            return result

        # Get user identifier
        user_id = state.get(self.user_id_key, "unknown")
        logger.info(f"Tagging with user_id: '{user_id}'")

        # Tag resources
        logger.info(f"Tagging {len(resources_created)} deployed resources")
        tagging_results = self._tag_resources(resources_created, user_id)

        logger.info(
            f"Tagging completed: {tagging_results['successful_tags']}/{tagging_results['total_resources']} successful"
        )

        # Create user-friendly message
        deployment_name = result_dict.get("deployment_id", "deployment")
        duration = result_dict.get("duration_seconds", 0)

        # Build a friendly message about the deployment and tagging
        friendly_message = f"Deployment {deployment_name} completed successfully in {duration:.2f}s"

        if tagging_results["successful_tags"] > 0:
            friendly_message += f"\nTagged {tagging_results['successful_tags']} resource(s)"

        if tagging_results["failed_tags"] > 0:
            friendly_message += (
                f"\nWarning: Failed to tag {tagging_results['failed_tags']} resource(s)"
            )

        # Handle different result types
        messages = []
        if isinstance(result, Command):
            # Get the original ToolMessage from Command
            if result.update is not None:
                messages = result.update.get("messages", [])

            if messages and isinstance(messages[0], ToolMessage):
                tool_message = ToolMessage(
                    content=friendly_message,
                    tool_call_id=messages[0].tool_call_id,
                )
            else:
                logger.warning("Could not find ToolMessage in Command to update")
                return result

            # Merge the original Command update with our tagging results
            updated_command = Command(
                update={
                    **(result.update or {}),  # Keep original updates
                    "tagging_results": tagging_results,
                    "messages": [tool_message],  # Replace with friendly message
                }
            )
            return updated_command

        elif isinstance(result, ToolMessage):
            # Replace JSON with user-friendly message
            tool_message = ToolMessage(
                content=friendly_message,
                tool_call_id=result.tool_call_id,
            )

            # Return updated result through Command to also update state
            return Command(
                update={
                    "tagging_results": tagging_results,
                    "messages": [tool_message],
                }
            )

        else:
            logger.warning(f"Unexpected result type after tagging: {type(result)}")
            return result

    def _tag_resources(self, resources: list[dict], user_id: str) -> dict:
        """Tag a list of Azure resources.

        Args:
            resources: List of resource dicts with 'id', 'name', 'type'
            user_id: User identifier for deployer tag

        Returns:
            Dictionary with tagged_resources, failed_resources, and metadata
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

        logger.debug(f"Resources to tag: {[r.get('name', r.get('id')) for r in resources]}")

        for resource in resources:
            resource_id = resource.get("id")
            if not resource_id:
                logger.warning(f"Skipping resource with no ID: {resource}")
                continue

            try:
                self._tag_resource(resource_id, tags)
                tagged_resources.append(
                    {
                        "id": resource_id,
                        "name": resource.get("name"),
                        "type": resource.get("type"),
                        "tags": tags,
                    }
                )
                logger.debug(f"Tagged resource: {resource_id}")

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
                    # Log full error with resource details
                    logger.warning(
                        f"Failed to tag resource: {resource.get('name')} "
                        f"(type: {resource.get('type')}) - Error: {error_msg}"
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

    def _tag_resource(self, resource_id: str, tags: dict[str, str]) -> None:
        """Tag a single Azure resource using Azure CLI.

        Args:
            resource_id: Full Azure resource ID
            tags: Dictionary of tag key-value pairs

        Raises:
            subprocess.CalledProcessError: If tagging command fails
        """
        # Build tag arguments
        tag_args = [f"{key}={value}" for key, value in tags.items()]

        # Build Azure CLI command
        # Note: az resource tag merges with existing tags by default
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

        logger.debug(f"Tagging command: {' '.join(cmd)}")

        # Execute tagging command
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,  # Don't raise exception, we'll check return code
                timeout=30,
            )

            # Check if command succeeded
            if result.returncode != 0:
                error_detail = result.stderr.strip() if result.stderr else "Unknown error"
                raise RuntimeError(
                    f"Tagging command failed (exit code {result.returncode}): {error_detail}"
                )

        except subprocess.TimeoutExpired:
            raise RuntimeError("Tagging command timed out after 30 seconds")
        except Exception:
            # Re-raise any other exceptions
            raise
