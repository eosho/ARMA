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


@tool("preview_what_if")
async def preview_what_if(
    subscription_id: str,
    resource_group: str,
    location: str,
    runtime: ToolRuntime,
) -> Command:
    """Run Azure what-if analysis to preview deployment changes.

    This tool analyzes what changes will occur if the deployment plan is executed.
    It reads the deployment_plan from state and runs Azure's what-if API.

    Requirements:
    - Must be called after plan_deployment
    - Requires deployment_plan in state

    Args:
        subscription_id: Azure subscription ID.
        resource_group: Name of the Azure resource group.
        location: Azure region (e.g., 'eastus').
        runtime: Tool runtime context (injected automatically).

    Returns:
        Command with updated state (what_if_results) and ToolMessage with change summary

    Examples:
        >>> result = await preview_what_if(
        ...     subscription_id="abc-123...",
        ...     resource_group="my-rg",
        ...     location="eastus"
        ... )
        >>> print(result)
        'What-if analysis: 3 changes detected (2 CREATE, 1 MODIFY)'
    """
    logger.debug(f"Running what-if: {subscription_id}/{resource_group}/{location}")

    deployment_plan = runtime.state.get("deployment_plan")

    if not deployment_plan:
        error_msg = (
            "No deployment plan found in state. "
            "You must call plan_deployment first before running what-if analysis."
        )
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

    arm_template = deployment_plan.get("arm_template")
    parameters = deployment_plan.get("parameters", {})
    deployment_scope = deployment_plan.get("deployment_scope", "resourceGroup")

    try:
        what_if_results = await run_what_if_deployment(
            resource_group=resource_group,
            location=location,
            template=arm_template,
            parameters=parameters,
            deployment_scope=deployment_scope,
        )

        if what_if_results.get("status") == "failed":
            error_msg = what_if_results.get("error", "Unknown error")
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"What-if analysis failed: {error_msg}",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )

        all_changes = what_if_results.get("changes", [])
        significant_changes = [
            change for change in all_changes if change.get("changeType") != "Ignore"
        ]

        change_types = {}
        for change in significant_changes:
            change_type = change.get("changeType", "UNKNOWN")
            change_types[change_type] = change_types.get(change_type, 0) + 1

        if significant_changes:
            summary_parts = [f"{count} {ctype}" for ctype, count in change_types.items()]

            resource_details = []
            for change in significant_changes[:5]:
                resource_id = change.get("resourceId", "unknown")
                change_type = change.get("changeType", "UNKNOWN")
                resource_name = resource_id.split("/")[-1] if resource_id else "unknown"
                resource_type = (
                    "/".join(resource_id.split("/")[-3:-1]) if resource_id else "unknown"
                )
                resource_details.append(f"  - {change_type}: {resource_type}/{resource_name}")

            if len(significant_changes) > 5:
                resource_details.append(f"  ... and {len(significant_changes) - 5} more changes")

            summary = (
                f"What-if analysis: {len(significant_changes)} change(s) detected ({', '.join(summary_parts)})\n"
                + "\n".join(resource_details)
            )
        else:
            summary = "What-if analysis: No changes detected (deployment is up to date)"

        logger.debug(summary)

        updated_plan = {**deployment_plan, "what_if_results": what_if_results}

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


@tool("plan_deployment")
async def plan_deployment(
    subscription_id: str,
    resource_group: str,
    location: str,
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
        subscription_id: Azure subscription ID.
        resource_group: Name of the Azure resource group.
        location: Azure region (e.g., 'eastus').
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
    logger.debug(f"Planning deployment: {template_path}")

    if deployment_scope == "resourceGroup":
        if not subscription_id:
            raise ValueError("Resource group deployment requires subscription_id parameter")
        if not resource_group:
            raise ValueError("Resource group deployment requires resource_group parameter")
        if not location:
            raise ValueError("Resource group deployment requires location parameter")
    elif deployment_scope == "subscription":
        if not subscription_id:
            raise ValueError("Subscription deployment requires subscription_id parameter")
        if not location:
            raise ValueError("Subscription deployment requires location parameter")
    elif deployment_scope in ["managementGroup", "tenant"]:
        raise ValueError(f"Deployment scope '{deployment_scope}' is not yet supported")
    else:
        raise ValueError(f"Invalid deployment scope: {deployment_scope}")

    logger.debug(
        f"Creating plan: subscription={subscription_id}, "
        f"resource_group={resource_group}, location={location}, scope={deployment_scope}"
    )

    try:
        logger.debug("Compiling Bicep template to ARM")
        arm_template = await compile_bicep_to_arm(template_path)

        logger.debug("Extracting template parameters")
        template_params = get_template_parameters(template_path)

        param_defaults = {
            p["name"]: p.get("default_value") for p in template_params if "default_value" in p
        }

        merged_parameters = {**param_defaults, **parameters}

        logger.debug(
            f"Parameters: {len(merged_parameters)} total "
            f"({len(parameters)} user-provided, {len(param_defaults)} defaults)"
        )
        logger.debug(f"Merged parameters: {merged_parameters}")

        resources = arm_template.get("resources", [])
        resource_count = len(resources)
        summary = f"Deployment plan created for {resource_count} resource(s)"

        deployment_plan = {
            "summary": summary,
            "subscription_id": subscription_id,
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

        logger.debug(f"Deployment plan created: {summary}")

        return Command(
            update={
                "deployment_plan": deployment_plan,
                "subscription_id": subscription_id,
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
