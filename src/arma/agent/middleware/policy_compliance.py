"""Azure Policy Compliance middleware for deployment validation.

Validates deployments against Azure Policy before execution to prevent violations.
Checks existing policy states and assignments, then blocks plan_deployment if
vio lations would occur. This runs BEFORE What-If analysis to fail fast.
"""

import subprocess
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from arma.agent.state import ARMAAgentState
from arma.agent.tools.utils.policy_helpers import (
    evaluate_policy_compliance,
    format_violation_message,
)
from arma.core.logging import get_logger

logger = get_logger(__name__)


class AzurePolicyComplianceMiddleware(AgentMiddleware):
    """Middleware to validate deployments against Azure Policy.

    Intercepts plan_deployment tool calls and validates against Azure Policy
    assignments. Blocks deployments that would violate Deny policies.
    """

    state_schema = ARMAAgentState

    def __init__(
        self,
        check_on_execute: bool = True,
        block_on_violations: bool = True,
        fail_on_policy_error: bool = False,
        include_warnings: bool = True,
    ) -> None:
        """Initialize Azure Policy Compliance middleware.

        Args:
            check_on_execute: Check policy before plan_deployment (default: True)
            block_on_violations: Block if Deny policy violations found (default: True)
            fail_on_policy_error: Fail if policy check errors (default: False)
            include_warnings: Include Audit policy warnings (default: True)
        """
        super().__init__()
        self.check_on_execute = check_on_execute
        self.block_on_violations = block_on_violations
        self.fail_on_policy_error = fail_on_policy_error
        self.include_warnings = include_warnings

    @property
    def name(self) -> str:
        """Return the middleware name identifier."""
        return "policy_compliance"

    async def awrap_tool_call(
        self, request: Any, handler: Callable[[Any], Any]
    ) -> Command | ToolMessage:
        """Async wrapper to validate policy compliance before plan_deployment.

        Args:
            request: Tool call request
            handler: Async function to call the actual tool

        Returns:
            Command with state updates or ToolMessage with results
        """
        return await self._check_policy_and_execute(request, handler)

    async def _check_policy_and_execute(
        self, request: Any, handler: Callable[[Any], Any]
    ) -> Command | ToolMessage:
        """Core async policy checking logic for plan_deployment.

        Args:
            request: Tool call request
            handler: Function to call the actual tool

        Returns:
            Command with state updates or ToolMessage with results
        """
        # Extract tool information - request.tool is the tool object, not string
        tool_obj = getattr(request, "tool", None)
        tool_name = getattr(tool_obj, "name", "") if tool_obj else request.tool_call.get("name", "")
        tool_call_id = request.tool_call.get("id", "")

        if tool_name != "plan_deployment" or not self.check_on_execute:
            result = await handler(request)
            return result

        logger.debug("Policy compliance check starting")

        state = request.runtime.state
        subscription_id = state.get("subscription_id")
        resource_group = state.get("resource_group")

        try:
            resource_type = state.get("resource_type", "")

            logger.debug(f"Evaluating policy compliance: {subscription_id}/{resource_group}")
            compliance_result = evaluate_policy_compliance(
                subscription_id=subscription_id,
                resource_group=resource_group,
                resource_type=resource_type,
                include_warnings=self.include_warnings,
            )

            violations = compliance_result.get("violations", [])
            warnings = compliance_result.get("warnings", [])

            logger.debug(f"Policy check: {len(violations)} violations, {len(warnings)} warnings")
            state_updates: dict[str, Any] = {
                "policy_check_status": "completed",
                "policy_violations": violations,
                "policy_warnings": warnings,
            }

            if violations and self.block_on_violations:
                logger.warning(f"Blocking deployment: {len(violations)} policy violations")
                error_message = format_violation_message(violations, warnings)

                return Command(
                    update={
                        **state_updates,
                        "messages": [
                            ToolMessage(
                                content=(
                                    f"Deployment blocked by Azure Policy {error_message} "
                                    "**Next Steps:** "
                                    "1. Review the policy violations above "
                                    "2. Update your deployment to comply with policies "
                                    "3. Or request a policy exemption from your administrator "
                                    "Inform the user tehy cannot proceed."
                                ),
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )

            if violations:
                logger.warning("Policy violations found but blocking disabled")

            if warnings:
                logger.debug(f"Policy warnings: {len(warnings)} audit policies")

            logger.debug("Policy check passed")
            result = await handler(request)

            if isinstance(result, Command):
                result_updates = {**(result.update or {}), **state_updates}
                return Command(
                    update=result_updates,
                    resume=result.resume,
                    goto=result.goto,
                )

            return result

        except subprocess.TimeoutExpired:
            logger.error("Policy check timed out")
            if self.fail_on_policy_error:
                return Command(
                    update={
                        "policy_check_status": "error",
                        "messages": [
                            ToolMessage(
                                content="Policy check timed out. Deployment blocked.",
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )
            result = await handler(request)
            return result

        except Exception as e:
            logger.error(f"Error during policy check: {e}", exc_info=True)
            if self.fail_on_policy_error:
                return Command(
                    update={
                        "policy_check_status": "error",
                        "messages": [
                            ToolMessage(
                                content=f"Policy check failed: {str(e)}. Deployment blocked.",
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )
            result = await handler(request)
            return result
