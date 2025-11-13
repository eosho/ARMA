"""Plan deployment tool.

This tool compiles Bicep to ARM and runs what-if analysis to preview changes.
"""

from typing import Any

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from arma.agent.tools.utils import (
    compile_bicep_to_arm,
    get_template_parameters,
    run_what_if_deployment,
)
from arma.core.logging import get_logger

logger = get_logger(__name__)


@tool
async def preview_what_if(
    runtime: ToolRuntime,
) -> Command:
    """Run Azure what-if analysis to preview deployment changes.

    This tool analyzes what changes will occur if the deployment plan is executed.
    It reads the deployment_plan from state and runs Azure's what-if API.

    Requirements:
    - Must be called after plan_deployment
    - Requires deployment_plan in state

    Returns:
        Command with updated state (what_if_results) and ToolMessage with change summary

    Examples:
        >>> result = await preview_what_if()
        >>> print(result)
        'What-if analysis: 3 changes detected (2 CREATE, 1 MODIFY)'
    """
    logger.info("Running what-if analysis")

    # Get context from state
    deployment_plan = runtime.state.get("deployment_plan")
    subscription_id = runtime.state.get("subscription_id")
    resource_group = runtime.state.get("resource_group")
    location = runtime.state.get("location")

    # Validate deployment plan exists
    if not deployment_plan:
        error_msg = (
            "No deployment plan found in state. "
            "You must call plan_deployment first before running what-if analysis."
        )
        logger.error(error_msg)
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Error: {error_msg}",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    # Extract deployment details from plan (with fallback to state)
    arm_template = deployment_plan.get("arm_template")
    parameters = deployment_plan.get("parameters", {})
    deployment_scope = deployment_plan.get("deployment_scope", "resourceGroup")

    # Use context from deployment_plan if available (fallback to state)
    subscription_id = deployment_plan.get("subscription_id", subscription_id)
    resource_group = deployment_plan.get("resource_group", resource_group)
    location = deployment_plan.get("location", location)

    # Validate required context
    if not subscription_id or not resource_group or not location:
        error_msg = "Missing Azure context (subscription_id, resource_group, location) in state"
        logger.error(error_msg)
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Error: {error_msg}",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    try:
        # Run what-if analysis
        what_if_results = await run_what_if_deployment(
            resource_group=resource_group,
            location=location,
            template=arm_template,
            parameters=parameters,
            deployment_scope=deployment_scope,
        )

        # Analyze changes
        changes = what_if_results.get("changes", [])
        change_types = {}
        for change in changes:
            change_type = change.get("changeType", "UNKNOWN")
            change_types[change_type] = change_types.get(change_type, 0) + 1

        # Build summary
        if changes:
            summary_parts = [f"{count} {ctype}" for ctype, count in change_types.items()]
            summary = (
                f"What-if analysis: {len(changes)} change(s) detected ({', '.join(summary_parts)})"
            )
        else:
            summary = "What-if analysis: No changes detected"

        logger.info(summary)

        # Update deployment plan with what-if results
        updated_plan = {**deployment_plan, "what_if_results": what_if_results}

        # Return Command with state updates
        return Command(
            update={
                "what_if_results": what_if_results,
                "deployment_plan": updated_plan,
                "messages": [
                    ToolMessage(
                        content=summary,
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    except Exception as e:
        error_msg = f"What-if analysis failed: {e}"
        logger.error(error_msg)
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Error: {error_msg}",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )


@tool
async def plan_deployment(
    template_path: str,
    parameters: dict[str, Any],
    deployment_scope: str,
    runtime: ToolRuntime,
) -> Command:
    """Generate a deployment plan from Bicep template.

    This tool:
    1. Compiles Bicep template to ARM JSON
    2. Merges user parameters with template defaults
    3. Extracts resource information
    4. Returns comprehensive deployment plan

    Note: This does NOT run what-if analysis. Call preview_what_if() separately for that.

    Args:
        template_path: Path to Bicep template file (from template discovery).
        parameters: User-provided parameter values only. Template defaults are merged automatically.
        deployment_scope: Deployment scope: 'resourceGroup', 'subscription', 'managementGroup', 'tenant'.
        runtime: Tool runtime context (injected automatically).

    Returns:
        Command with updated state (deployment_plan, parameters) and ToolMessage

    Examples:
        >>> plan = await plan_deployment(
        ...     template_path="/path/to/main.bicep",
        ...     parameters={"storageAccountName": "myacct123"},
        ...     deployment_scope="resourceGroup"
        ... )
        >>> print(plan["summary"])
        'Deployment plan created for 3 resource(s)'
    """
    logger.info(f"Planning deployment: {template_path}")

    # GUARD: Check if template is available (discovery succeeded and template_path exists)
    template_discovery_status = runtime.state.get("template_discovery_status")
    state_template_path = runtime.state.get("template_path")

    if template_discovery_status == "failed" or not state_template_path:
        error_msg = runtime.state.get("template_discovery_error", "No template found")
        logger.error(f"Cannot plan deployment - template not available: {error_msg}")
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"ERROR: Cannot create deployment plan. {error_msg}. "
                            f"Please inform the user that this resource type is not supported yet."
                        ),
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    # Get context from state with detailed logging
    subscription_id = runtime.state.get("subscription_id")
    resource_group = runtime.state.get("resource_group")
    location = runtime.state.get("location")

    # Debug logging - check actual values not just presence
    logger.debug(f"State keys available: {list(runtime.state.keys())[:20]}")
    logger.debug(
        f"Retrieved context - subscription_id: '{subscription_id}' (type: {type(subscription_id).__name__})"
    )
    logger.debug(
        f"Retrieved context - resource_group: '{resource_group}' (type: {type(resource_group).__name__})"
    )
    logger.debug(f"Retrieved context - location: '{location}' (type: {type(location).__name__})")

    # Validate required context based on scope
    if deployment_scope == "resourceGroup":
        if not subscription_id:
            logger.error(
                f"subscription_id missing from state. Available keys: {list(runtime.state.keys())}"
            )
            logger.error(
                f"subscription_id VALUE: '{subscription_id}' (empty={not subscription_id})"
            )
            # Try to get the actual value directly
            logger.error(
                f"Direct access: runtime.state['subscription_id'] = '{runtime.state.get('subscription_id', 'KEY_NOT_FOUND')}'"
            )
            raise ValueError("Resource group deployment requires subscription_id in state")
        if not resource_group:
            logger.error(
                f"resource_group missing from state. Available keys: {list(runtime.state.keys())}"
            )
            raise ValueError("Resource group deployment requires resource_group in state")
        if not location:
            logger.error(
                f"location missing from state. Available keys: {list(runtime.state.keys())}"
            )
            raise ValueError("Resource group deployment requires location in state")
    elif deployment_scope == "subscription":
        if not subscription_id:
            raise ValueError("Subscription deployment requires subscription_id in state")
        if not location:
            raise ValueError("Subscription deployment requires location in state")
    elif deployment_scope in ["managementGroup", "tenant"]:
        raise ValueError(f"Deployment scope '{deployment_scope}' is not yet supported")
    else:
        raise ValueError(f"Invalid deployment scope: {deployment_scope}")

    try:
        # Step 1: Compile Bicep to ARM
        logger.info("Compiling Bicep template to ARM")
        arm_template = await compile_bicep_to_arm(template_path)

        # Step 2: Get template parameters with defaults
        logger.info("Extracting template parameters")
        template_params = get_template_parameters(template_path)

        # Build parameter map: {name: default_value}
        param_defaults = {
            p["name"]: p.get("default_value") for p in template_params if "default_value" in p
        }

        # Step 3: Merge user parameters with defaults
        # User parameters take precedence over defaults
        merged_parameters = {**param_defaults, **parameters}

        logger.info(
            f"Parameters: {len(merged_parameters)} total "
            f"({len(parameters)} user-provided, {len(param_defaults)} defaults)"
        )
        logger.debug(f"Merged parameters: {merged_parameters}")

        # Step 4: Extract resources from ARM template
        resources = arm_template.get("resources", [])
        resource_count = len(resources)

        # Step 5: Generate human-readable summary
        summary = f"Deployment plan created for {resource_count} resource(s)"

        # Build deployment plan
        deployment_plan = {
            "summary": summary,
            "subscription_id": subscription_id,  # Preserve Azure context
            "resource_group": resource_group,
            "location": location,
            "resources": [
                {
                    "name": r.get("name", "unknown"),
                    "type": r.get("type", "unknown"),
                    "location": r.get("location", location),
                }
                for r in resources
            ],
            "parameters": merged_parameters,
            "parameter_count": {
                "total": len(merged_parameters),
                "user_provided": len(parameters),
                "defaults": len(param_defaults),
            },
            "template_path": template_path,
            "deployment_scope": deployment_scope,
            "arm_template": arm_template,
        }

        logger.info(f"Deployment plan created: {summary}")

        # Return Command with state updates and ToolMessage
        # Explicitly preserve subscription_id, resource_group, location in state
        return Command(
            update={
                "deployment_plan": deployment_plan,
                "subscription_id": subscription_id,  # Preserve in state
                "resource_group": resource_group,
                "location": location,
                "parameters": merged_parameters,
                "messages": [
                    ToolMessage(
                        content=f"{summary}. Call preview_what_if() to see what changes will occur.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    except FileNotFoundError as e:
        error_msg = f"Template file not found: {e}"
        logger.error(error_msg)
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Error: {error_msg}",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )
    except Exception as e:
        error_msg = f"Failed to create deployment plan: {e}"
        logger.error(error_msg)
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Error: {error_msg}",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )
