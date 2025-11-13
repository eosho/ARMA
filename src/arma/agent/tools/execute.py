"""Execute deployment tool.

This tool executes an Azure deployment with the specified template and parameters.
"""

import json
import os
import subprocess
import tempfile
import time
from typing import Any

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from arma.core.logging import get_logger

logger = get_logger(__name__)


@tool
async def execute_deployment(
    runtime: ToolRuntime,
) -> Command:
    """Execute an Azure deployment using the plan from state.

    This tool deploys a Bicep template to Azure using the deployment_plan
    created by plan_deployment. All necessary information (template, parameters,
    scope, location, etc.) is read from the deployment_plan in state.

    Requirements:
    - Must be called after plan_deployment
    - Requires deployment_plan in state with all deployment details

    Args:
        runtime: Tool runtime context (injected automatically).

    Returns:
        Command with updated state and ToolMessage containing deployment results.

    Examples:
        >>> # After plan_deployment has been called
        >>> result = await execute_deployment()
    """
    logger.info("Starting execute_deployment")

    # Get deployment plan from state
    deployment_plan = runtime.state.get("deployment_plan")
    if not deployment_plan:
        error_msg = (
            "No deployment plan found in state. "
            "You must call plan_deployment first before executing deployment."
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

    # Extract deployment details from plan
    template_file = deployment_plan.get("template_path")
    parameters = deployment_plan.get("parameters", {})
    deployment_scope = deployment_plan.get("deployment_scope", "resourceGroup")
    subscription_id = deployment_plan.get("subscription_id")
    resource_group = deployment_plan.get("resource_group")
    location = deployment_plan.get("location")
    arm_template = deployment_plan.get("arm_template")

    # Generate deployment name
    deployment_name = f"arma-deploy-{int(time.time())}"

    # Validate required fields from deployment plan
    if not subscription_id:
        error_msg = "Missing subscription_id in deployment plan"
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

    if not template_file:
        error_msg = "Missing template_path in deployment plan"
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

    # Validate scope-specific requirements
    if deployment_scope == "resourceGroup":
        if not resource_group:
            error_msg = "Resource group deployment requires resource_group in deployment plan"
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
    elif deployment_scope == "subscription":
        if not location:
            error_msg = "Subscription deployment requires location in deployment plan"
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
    else:
        error_msg = f"Unsupported deployment scope: {deployment_scope}"
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

    logger.debug(
        f"Deployment context: scope={deployment_scope}, resource_group={resource_group}, location={location}"
    )
    logger.info(f"Executing deployment '{deployment_name}' to {resource_group or location}")

    start_time = time.time()

    try:
        # Use ARM template from deployment plan if available (already compiled)
        if arm_template:
            logger.debug("Using ARM template from deployment plan")
        else:
            # Compile Bicep template to ARM JSON as fallback
            logger.debug(f"Compiling Bicep template: {template_file}")
            bicep_result = subprocess.run(
                ["az", "bicep", "build", "--file", template_file, "--stdout"],
                capture_output=True,
                text=True,
                check=True,
            )
            arm_template = json.loads(bicep_result.stdout)

        # Write ARM template to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(arm_template, f)
            arm_template_file = f.name

        # Write parameters to temp file
        params_formatted = {key: {"value": value} for key, value in parameters.items()}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"parameters": params_formatted}, f)
            params_file = f.name

        try:
            # Build deployment command based on scope
            if deployment_scope == "resourceGroup":
                cmd = [
                    "az",
                    "deployment",
                    "group",
                    "create",
                    "--resource-group",
                    resource_group,
                    "--name",
                    deployment_name,
                    "--template-file",
                    template_file,
                    "--parameters",
                    params_file,
                ]
            elif deployment_scope == "subscription":
                cmd = [
                    "az",
                    "deployment",
                    "sub",
                    "create",
                    "--location",
                    location,
                    "--name",
                    deployment_name,
                    "--template-file",
                    template_file,
                    "--parameters",
                    params_file,
                ]
            else:
                raise ValueError(f"Unsupported deployment scope: {deployment_scope}")

            logger.info(f"Starting deployment: {deployment_name}")
            logger.debug(f"Command: {' '.join(cmd)}")

            # Execute deployment
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            # Parse deployment result
            deployment_output = json.loads(result.stdout)

            duration = time.time() - start_time

            execution_result = {
                "deployment_id": deployment_name,
                "status": "completed",
                "outputs": deployment_output.get("properties", {}).get("outputs", {}),
                "resources_created": _extract_resources_from_deployment(deployment_output),
                "errors": [],
                "duration_seconds": round(duration, 2),
                "deployment_details": {
                    "provisioning_state": deployment_output.get("properties", {}).get(
                        "provisioningState"
                    ),
                    "correlation_id": deployment_output.get("properties", {}).get("correlationId"),
                    "timestamp": deployment_output.get("properties", {}).get("timestamp"),
                },
            }

            logger.info(f"Deployment completed successfully: {deployment_name} ({duration:.2f}s)")

            # Return Command with state updates and ToolMessage
            return Command(
                update={
                    "deployment_id": deployment_name,
                    "deployment_status": "completed",
                    "deployment_outputs": execution_result["outputs"],
                    "deployment_errors": [],
                    "messages": [
                        ToolMessage(
                            content=json.dumps(execution_result),
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )

        finally:
            # Clean up temp files
            try:
                os.unlink(arm_template_file)
                os.unlink(params_file)
            except OSError:
                pass

    except subprocess.CalledProcessError as e:
        duration = time.time() - start_time
        error_msg = e.stderr if e.stderr else str(e)
        logger.error(f"Deployment failed: {error_msg}")

        return Command(
            update={
                "deployment_id": deployment_name,
                "deployment_status": "failed",
                "deployment_outputs": {},
                "deployment_errors": [error_msg],
                "messages": [
                    ToolMessage(
                        content=f"Deployment {deployment_name} failed: {error_msg}",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Deployment error: {e}")

        return Command(
            update={
                "deployment_id": deployment_name,
                "deployment_status": "failed",
                "deployment_outputs": {},
                "deployment_errors": [str(e)],
                "messages": [
                    ToolMessage(
                        content=f"Deployment error: {str(e)}",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )


def _extract_resources_from_deployment(deployment_output: dict[str, Any]) -> list[dict[str, str]]:
    """Extract created resources from deployment output.

    Args:
        deployment_output: Azure deployment result JSON

    Returns:
        List of resource dictionaries with id, name, and type
    """
    resources = []

    try:
        # Extract from output resources
        output_resources = deployment_output.get("properties", {}).get("outputResources", [])
        for resource in output_resources:
            resource_id = resource.get("id", "")
            if resource_id:
                # Parse resource ID to get name and type
                parts = resource_id.split("/")
                resource_name = parts[-1] if parts else "unknown"

                # Find resource type (format: Microsoft.Provider/resourceType)
                resource_type = "unknown"
                for i, part in enumerate(parts):
                    if "." in part and i + 1 < len(parts):
                        resource_type = f"{part}/{parts[i + 1]}"
                        break

                resources.append({"id": resource_id, "name": resource_name, "type": resource_type})
    except Exception as e:
        logger.warning(f"Error extracting resources from deployment: {e}")

    return resources
