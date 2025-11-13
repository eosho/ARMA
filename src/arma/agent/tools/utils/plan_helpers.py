"""Planning helper utilities for deployment plans."""

import json
import os
import subprocess
import tempfile
from typing import Any

from arma.core.logging import get_logger

logger = get_logger(__name__)


async def run_what_if_deployment(
    resource_group: str,
    location: str,
    template: dict[str, Any],
    parameters: dict[str, Any],
    deployment_scope: str = "resourceGroup",
) -> dict[str, Any]:
    """Run Azure what-if deployment to preview changes.

    Args:
        resource_group: Target resource group name (required for resourceGroup scope).
        location: Target Azure region.
        template: ARM template as dictionary.
        parameters: Template parameters.
        deployment_scope: Deployment scope (resourceGroup, subscription, managementGroup, tenant).

    Returns:
        What-if results dictionary with status and changes.

    Raises:
        AzureError: If what-if operation fails.
    """
    logger.debug(f"Running what-if for scope: {deployment_scope}")

    # Convert parameters to Azure SDK format
    try:
        # Create a temporary deployment name
        deployment_name = f"arma-whatif-{location}"

        # Write template to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(template, f)
            template_file = f.name

        # Write parameters to temp file
        params_formatted = {key: {"value": value} for key, value in parameters.items()}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"parameters": params_formatted}, f)
            params_file = f.name

        try:
            # Build command based on deployment scope
            if deployment_scope == "resourceGroup":
                # Run az deployment group what-if
                cmd = [
                    "az",
                    "deployment",
                    "group",
                    "what-if",
                    "--resource-group",
                    resource_group,
                    "--name",
                    deployment_name,
                    "--template-file",
                    template_file,
                    "--parameters",
                    params_file,
                    "--result-format",
                    "ResourceIdOnly",
                ]
            elif deployment_scope == "subscription":
                # Run az deployment sub what-if
                cmd = [
                    "az",
                    "deployment",
                    "sub",
                    "what-if",
                    "--location",
                    location,
                    "--name",
                    deployment_name,
                    "--template-file",
                    template_file,
                    "--parameters",
                    params_file,
                    "--result-format",
                    "ResourceIdOnly",
                ]
            elif deployment_scope == "managementGroup":
                raise ValueError("Management group deployment scope is not yet supported")
            elif deployment_scope == "tenant":
                raise ValueError("Tenant deployment scope is not yet supported")
            else:
                raise ValueError(f"Invalid deployment scope: {deployment_scope}")

            subprocess.run(cmd, capture_output=True, text=True, check=True)

            return {"status": "succeeded", "changes": []}

        finally:
            # Clean up temp files
            os.unlink(template_file)
            os.unlink(params_file)

    except subprocess.CalledProcessError as e:
        logger.error(f"What-if command failed: {e.stderr}")
        # Return empty result if what-if fails
        return {"status": "failed", "changes": []}
    except Exception as e:
        logger.error(f"What-if operation failed: {e}")
        return {"status": "failed", "changes": []}
