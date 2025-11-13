"""Azure Policy Compliance middleware for deployment validation.

This middleware validates deployments against Azure Policy before execution to prevent
policy violations. It wraps the execute_deployment tool and checks:
1. Policy assignments for the target scope (subscription/resource group)
2. What-If analysis to preview deployment changes
3. Deny policies that would block the deployment
4. Audit policies for compliance warnings

If violations are detected, the middleware blocks execution and returns a detailed
error message with remediation suggestions.
"""

import json
import subprocess
from typing import Any, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from arma.agent.tools.utils.policy_helpers import (
    evaluate_policy_compliance,
    format_violation_message,
    get_policy_assignments,
    run_what_if_analysis,
)
from arma.core.logging import get_logger

logger = get_logger(__name__)


class AzurePolicyComplianceMiddleware(AgentMiddleware):
    """Middleware to validate deployments against Azure Policy.

    This middleware intercepts plan_deployment tool calls and validates them
    against Azure Policy assignments before allowing the plan to be created.
    It prevents deployments that would violate Deny policies and provides
    warnings for Audit policies.
    """

    def __init__(
        self,
        check_on_execute: bool = True,
        block_on_violations: bool = True,
        fail_on_policy_error: bool = False,
        include_warnings: bool = True,
        skip_what_if: bool = False,
    ) -> None:
        """Initialize Azure Policy Compliance middleware.

        Args:
            check_on_execute: Check policy compliance before plan_deployment (default: True)
            block_on_violations: Block deployment if Deny policy violations found (default: True)
            fail_on_policy_error: Fail if policy check errors (False = warn and allow, default: False)
            include_warnings: Include Audit policy warnings in results (default: True)
            skip_what_if: Skip What-If analysis for faster checks (default: False, not recommended)
        """
        super().__init__()
        self.check_on_execute = check_on_execute
        self.block_on_violations = block_on_violations
        self.fail_on_policy_error = fail_on_policy_error
        self.include_warnings = include_warnings
        self.skip_what_if = skip_what_if

    @property
    def name(self) -> str:
        """Return the middleware name identifier."""
        return "policy_compliance"

    async def awrap_tool_call(
        self, request: Any, handler: Callable[[Any], Any]
    ) -> Command | ToolMessage:
        """Async wrapper for tool calls to validate policy compliance before plan_deployment.

        Args:
            request: Tool call request with tool name, arguments, and runtime context
            handler: Async function to call the actual tool implementation

        Returns:
            Command with state updates or ToolMessage with results/errors
        """
        return await self._check_policy_and_execute(request, handler)

    async def _check_policy_and_execute(
        self, request: Any, handler: Callable[[Any], Any]
    ) -> Command | ToolMessage:
        """Core async policy checking logic for plan_deployment tool.

        Args:
            request: Tool call request with tool name, arguments, and runtime context
            handler: Function to call the actual tool implementation

        Returns:
            Command with state updates or ToolMessage with results/errors
        """
        # Extract tool information - request.tool is the tool object, not string
        tool_obj = getattr(request, "tool", None)
        if tool_obj:
            # Tool object has a 'name' attribute
            tool_name = getattr(tool_obj, "name", "")
        else:
            # Fallback to tool_call dict
            tool_name = request.tool_call.get("name", "")

        tool_call_id = request.tool_call.get("id", "")

        # Only check policy for plan_deployment tool
        if tool_name != "plan_deployment" or not self.check_on_execute:
            result = await handler(request)
            return result

        # Policy check triggered - log detailed info
        logger.info("Policy compliance check starting before deployment planning")

        # Get state from runtime
        state = request.runtime.state
        subscription_id = state.get("subscription_id")
        resource_group = state.get("resource_group")

        logger.info(f"Target: subscription_id={subscription_id}, resource_group={resource_group}")

        # Get plan details from tool arguments (plan hasn't been created yet)
        tool_args = getattr(request, "tool_input", {})
        template_path = tool_args.get("template_path", state.get("template_path"))
        parameters = tool_args.get("parameters", {})
        deployment_scope = tool_args.get("deployment_scope", "resourceGroup")

        # Validate we have required context
        if not subscription_id:
            logger.warning("Cannot check policy: subscription_id not in state")
            if self.fail_on_policy_error:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                content="Policy check failed: subscription_id required",
                                tool_call_id=tool_call_id,
                            )
                        ]
                    }
                )
            logger.warning("Proceeding without policy check (fail_on_policy_error=False)")
            result = await handler(request)
            return result

        if not resource_group:
            logger.warning("Cannot check policy: resource_group not in state")
            if self.fail_on_policy_error:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                content="Policy check failed: resource_group required",
                                tool_call_id=tool_call_id,
                            )
                        ]
                    }
                )
            logger.warning("Proceeding without policy check (fail_on_policy_error=False)")
            result = await handler(request)
            return result

        if not template_path:
            logger.warning("Cannot check policy: template_path not available")
            if self.fail_on_policy_error:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                content="Policy check failed: template_path required",
                                tool_call_id=tool_call_id,
                            )
                        ]
                    }
                )
            logger.warning("Proceeding without policy check (fail_on_policy_error=False)")
            result = await handler(request)
            return result

        try:
            # Step 1: Get policy assignments for scope
            logger.info(
                f"Fetching policy assignments for subscription={subscription_id}, resource_group={resource_group}"
            )
            policy_assignments = get_policy_assignments(subscription_id, resource_group)
            logger.info(f"Found {len(policy_assignments)} policy assignments")

            # Step 2: Run What-If analysis (unless skipped)
            what_if_results = None
            if not self.skip_what_if:
                logger.info("Running What-If analysis for policy check...")
                what_if_results = run_what_if_analysis(
                    subscription_id, resource_group, template_path, parameters
                )
                logger.info("What-If analysis completed")

            # Step 3: Evaluate policy compliance
            logger.info("Evaluating policy compliance...")

            # Extract resource type and location for evaluation
            resource_type = state.get("resource_type", "")
            # Location priority: parameters > state
            location = parameters.get("location") or state.get("location", "")

            logger.debug(f"Policy eval context: resource_type={resource_type}, location={location}")
            logger.debug(f"Parameters: {parameters}")
            logger.debug(f"State location: {state.get('location')}")            # Build a deployment plan structure for evaluation
            plan_for_eval = {
                "template_path": template_path,
                "parameters": parameters,
                "deployment_scope": deployment_scope,
                "resource_group": resource_group,
                "subscription_id": subscription_id,
                "resource_type": resource_type,
                "location": location,
            }

            compliance_result = evaluate_policy_compliance(
                policy_assignments=policy_assignments,
                what_if_results=what_if_results,
                deployment_plan=plan_for_eval,
                resource_type=resource_type,
                location=location,
                include_warnings=self.include_warnings,
            )

            violations = compliance_result.get("violations", [])
            warnings = compliance_result.get("warnings", [])

            logger.info(
                f"Policy evaluation complete: {len(violations)} violations, {len(warnings)} warnings"
            )

            # Step 4: Update state with compliance results
            state_updates: dict[str, Any] = {
                "policy_check_status": "completed",
                "policy_violations": violations,
                "policy_warnings": warnings,
            }

            # Step 5: Block if violations found and blocking enabled
            if violations and self.block_on_violations:
                logger.warning(f"Blocking deployment due to {len(violations)} policy violations")
                error_message = format_violation_message(violations, warnings)

                return Command(
                    update={
                        **state_updates,
                        "messages": [
                            ToolMessage(
                                content=f"❌ Deployment blocked by Azure Policy:\n\n{error_message}",
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )

            # No violations or blocking disabled - allow deployment
            if violations:
                logger.warning(
                    f"Policy violations found but blocking disabled (block_on_violations=False)"
                )

            if warnings:
                logger.info(f"Policy warnings: {len(warnings)} Audit policies will be logged")

            # Proceed with deployment
            logger.info("Policy check passed - proceeding with deployment")
            result = await handler(request)

            # Add policy check info to result if it's a Command
            if isinstance(result, Command):
                # Create new Command with merged updates (Command.update is frozen)
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
                                content="Policy check timed out. Deployment blocked for safety.",
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )
            logger.warning("Timeout during policy check - proceeding without validation")
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
                                content=f"Policy check failed: {str(e)}. Deployment blocked for safety.",
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )
            logger.warning(f"Error during policy check - proceeding without validation: {e}")
            result = await handler(request)
            return result
