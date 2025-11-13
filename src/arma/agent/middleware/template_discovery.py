"""Template discovery middleware.

Automatically discovers and analyzes Bicep templates after resource validation.
Triggers when check_existing_resource tool is executed and extracts resource_type
from the tool result to find and analyze the appropriate Bicep template.
"""

import json
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from arma.agent.tools.utils import (
    find_template_for_resource_type,
    get_template_parameters,
    get_template_scope,
)
from arma.core.logging import get_logger

logger = get_logger(__name__)


class TemplateDiscoveryMiddleware(AgentMiddleware):
    """Automatically discovers Bicep templates after resource validation.

    The template discovery happens automatically and transparently, so the agent
    doesn't need to explicitly call template discovery tools. The discovered
    template information is immediately available for plan_deployment to use.

    Example:
        ```python
        from arma.agent.middleware import TemplateDiscoveryMiddleware
        from arma.agent.factory import create_agent

        # Middleware is automatically included in agent factory
        agent = create_agent(model="openai:gpt-4o")

        # When agent calls check_existing_resource, template discovery happens
        # automatically without explicit tool calls
        ```
    """

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable,
    ) -> ToolMessage | Command:
        """Async version of wrap_tool_call - wraps check_existing_resource tool calls.

        See wrap_tool_call for full documentation.
        """
        # Get tool name and args
        tool_name = request.tool_call.get("name", "")
        tool_args = request.tool_call.get("args", {})

        # Execute the tool
        result = await handler(request)

        logger.debug(f"TemplateDiscoveryMiddleware.awrap_tool_call: tool='{tool_name}'")

        # Only process check_existing_resource
        if tool_name != "check_existing_resource":
            logger.debug(f"Skipping template discovery - tool is '{tool_name}'")
            return result

        # Get state from request
        state = request.state

        # Extract resource_type from tool arguments
        resource_type = tool_args.get("resource_type")

        if not resource_type:
            logger.debug("No resource_type in tool args - skipping template discovery")
            return result

        logger.info(f"Discovering template for resource type: {resource_type}")
        logger.debug(f"Current state keys: {list(state.keys())}")

        # Check if template already discovered for this resource type
        current_template = state.get("template_path")
        current_resource_type = state.get("resource_type")

        if current_template and current_resource_type == resource_type:
            logger.info(
                f"Template already discovered for {resource_type}: {current_template} - "
                "enriching result with template info"
            )

            # Enrich the tool result with template information
            if isinstance(result, ToolMessage):
                try:
                    original_content: dict[str, Any] = {}

                    # Parse existing content
                    if isinstance(result.content, str):
                        try:
                            original_content = json.loads(result.content)
                        except json.JSONDecodeError:
                            # Plain text, create new dict
                            original_content = {"message": result.content}
                    elif isinstance(result.content, dict):
                        original_content = dict(result.content)

                    # Add template information
                    deployment_scope = state.get("deployment_scope")
                    template_parameters = state.get("template_parameters", [])
                    required_params = [p for p in template_parameters if p.get("required", False)]

                    original_content["template_available"] = True
                    original_content["template_path"] = current_template
                    original_content["deployment_scope"] = deployment_scope
                    original_content["required_parameters"] = [p["name"] for p in required_params]

                    result = ToolMessage(
                        content=json.dumps(original_content),
                        tool_call_id=result.tool_call_id,
                    )
                    logger.debug("Enriched result with existing template information")
                except (AttributeError, TypeError) as e:
                    logger.debug(f"Could not enrich result: {e}")

            return result

        try:
            # Find template
            template_path = find_template_for_resource_type(resource_type)

            if not template_path:
                logger.warning(f"No template found for resource type: {resource_type}")

                # Get tool_call_id from the request
                tool_call_id = request.tool_call.get("id")

                # Create error message for the LLM
                error_message = ToolMessage(
                    content=(
                        f"DEPLOYMENT NOT POSSIBLE: No Bicep template found for {resource_type}. "
                        f"This resource type is not currently supported. "
                        f"Please inform the user that {resource_type} deployments are not available yet."
                    ),
                    tool_call_id=tool_call_id,
                )

                # Return Command with state updates and error message
                return Command(
                    update={
                        "resource_type": resource_type,
                        "template_discovery_error": f"No template found for {resource_type}",
                        "template_discovery_status": "failed",
                        "messages": [error_message],
                    }
                )

            logger.info(f"Template found: {template_path}")

            # Get template information
            deployment_scope = get_template_scope(template_path)
            parameters = get_template_parameters(template_path)
            required_params = [p for p in parameters if p.get("required", False)]

            logger.info(
                f"Template info: scope={deployment_scope}, "
                f"params={len(parameters)}, required={len(required_params)}"
            )

            # Update state with template info
            state["resource_type"] = resource_type
            state["template_path"] = template_path
            state["deployment_scope"] = deployment_scope
            state["template_parameters"] = parameters
            state["template_discovery_status"] = "completed"

            # Modify the tool result to inform the LLM about template availability
            if isinstance(result, ToolMessage):
                try:
                    original_content: dict[str, Any] = {}

                    # Handle both string and dict content
                    if isinstance(getattr(result, "content", None), str):
                        # Try to parse as JSON
                        try:
                            content = result.content
                            if isinstance(content, str):
                                original_content = json.loads(content)
                            else:
                                logger.debug("Content is not a string - skipping JSON parsing")
                                return result
                        except json.JSONDecodeError:
                            # Content is plain text, not JSON
                            logger.debug(
                                "Tool result is plain text, not JSON - skipping modification"
                            )
                            return result
                    else:
                        logger.debug(
                            f"Tool result content type {type(getattr(result, 'content', None))} - skipping modification"
                        )
                        return result

                    # Add template information to the content
                    original_content["template_available"] = True
                    original_content["template_path"] = template_path
                    original_content["deployment_scope"] = deployment_scope
                    original_content["required_parameters"] = [p["name"] for p in required_params]

                    result = ToolMessage(
                        content=json.dumps(original_content),
                        tool_call_id=result.tool_call_id,
                    )
                    logger.debug("Updated tool result with template availability")
                except (json.JSONDecodeError, AttributeError, TypeError) as e:
                    logger.debug(f"Could not modify tool result: {e}")

            logger.info("Template discovery completed successfully")

            # Extract messages properly based on result type
            if isinstance(result, ToolMessage):
                messages = [result]
            elif isinstance(result, Command):
                # Extract messages from Command's update dict
                messages = result.update.get("messages", []) if result.update else []
            else:
                messages = []

            # Return Command with state updates to persist them
            return Command(
                update={
                    "resource_type": resource_type,
                    "template_path": template_path,
                    "deployment_scope": deployment_scope,
                    "template_parameters": parameters,
                    "template_discovery_status": "completed",
                    "messages": messages,
                }
            )

        except Exception as e:
            logger.error(f"Error during template discovery: {e}", exc_info=True)

            # Extract messages properly based on result type
            if isinstance(result, ToolMessage):
                messages = [result]
            elif isinstance(result, Command):
                messages = result.update.get("messages", []) if result.update else []
            else:
                messages = []

            # Return Command with error state updates
            return Command(
                update={
                    "resource_type": resource_type,
                    "template_discovery_error": f"Template discovery error: {str(e)}",
                    "template_discovery_status": "failed",
                    "messages": messages,
                }
            )
