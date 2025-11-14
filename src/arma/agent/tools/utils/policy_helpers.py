"""Policy compliance helper utilities for Azure Policy validation.

This module provides utilities to check Azure Policy compliance before deployments:
- Get policy assignments for a scope
- Run What-If analysis
- Evaluate policy compliance
- Format violation messages
"""

import json
import subprocess
from typing import Any

from arma.core.logging import get_logger

logger = get_logger(__name__)


def get_policy_assignments(
    subscription_id: str,
    resource_group: str | None = None,
) -> list[dict[str, Any]]:
    """Get policy assignments for a scope including inherited assignments.

    Args:
        subscription_id: Azure subscription ID
        resource_group: Optional resource group name

    Returns:
        List of policy assignments
    """
    try:
        cmd = [
            "az",
            "policy",
            "assignment",
            "list",
            "--subscription",
            subscription_id,
            "--disable-scope-strict-match",  # Include inherited assignments
            "-o",
            "json",
        ]

        # Add resource group filter if provided
        if resource_group:
            cmd.extend(["--resource-group", resource_group])

        logger.debug(f"Getting policy assignments for {subscription_id}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            assignments = json.loads(result.stdout)
            logger.debug(f"Retrieved {len(assignments)} policy assignments")
            return assignments
        else:
            logger.error(f"Failed to get policy assignments: {result.stderr}")
            return []

    except subprocess.TimeoutExpired:
        logger.error("Timeout getting policy assignments")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse policy assignments JSON: {e}")
        return []
    except Exception as e:
        logger.error(f"Error getting policy assignments: {e}")
        return []


def run_what_if_analysis(
    subscription_id: str,
    resource_group: str,
    template_path: str,
    parameters: dict[str, Any],
) -> dict[str, Any] | None:
    """Run Azure What-If analysis for a deployment.

    Args:
        subscription_id: Azure subscription ID
        resource_group: Resource group name
        template_path: Path to ARM template
        parameters: Deployment parameters

    Returns:
        What-If results or None if failed
    """
    try:
        # Write parameters to temporary file
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as param_file:
            json.dump({"parameters": parameters}, param_file)
            param_file_path = param_file.name

        try:
            cmd = [
                "az",
                "deployment",
                "group",
                "what-if",
                "--resource-group",
                resource_group,
                "--subscription",
                subscription_id,
                "--template-file",
                template_path,
                "--parameters",
                f"@{param_file_path}",
                "--no-pretty-print",
                "-o",
                "json",
            ]

            logger.debug(f"Running What-If: {' '.join(cmd[:8])}...")  # Don't log full command
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode == 0:
                what_if_result = json.loads(result.stdout)
                logger.debug("What-If analysis completed")
                return what_if_result
            else:
                logger.warning(f"What-If analysis failed: {result.stderr[:200]}")
                return None

        finally:
            # Clean up temp file
            import contextlib
            import os

            with contextlib.suppress(OSError):
                os.unlink(param_file_path)

    except subprocess.TimeoutExpired:
        logger.error("What-If analysis timed out")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse What-If results: {e}")
        return None
    except Exception as e:
        logger.error(f"Error running What-If analysis: {e}")
        return None


def evaluate_policy_compliance(
    policy_assignments: list[dict[str, Any]],
    what_if_results: dict[str, Any] | None,
    resource_type: str,
    location: str,
    include_warnings: bool = True,
) -> dict[str, Any]:
    """Evaluate policy compliance for a deployment.

    Args:
        policy_assignments: Policy assignments from get_policy_assignments
        what_if_results: Optional What-If results for improved accuracy
        resource_type: Resource type being deployed
        location: Target location
        include_warnings: Include Audit policy warnings

    Returns:
        Dict with 'violations' and 'warnings' lists
    """
    violations = []
    warnings = []

    logger.debug(
        f"Evaluating compliance: {resource_type} in {location} with {len(policy_assignments)} policies"
    )
    for assignment in policy_assignments:
        try:
            display_name = assignment.get("displayName", "Unknown Policy")
            policy_def_id = assignment.get("policyDefinitionId", "")

            enforcement_mode = assignment.get("enforcementMode", "Default")
            if enforcement_mode == "DoNotEnforce":
                logger.debug(f"Skipping policy '{display_name}' (DoNotEnforce)")
                continue
            if "allowed locations" in display_name.lower() or "location" in policy_def_id.lower():
                policy_params = assignment.get("parameters", {})
                allowed_locations_param = policy_params.get("listOfAllowedLocations", {})
                allowed_locations = allowed_locations_param.get("value", [])

                if (
                    allowed_locations
                    and location
                    and location.lower() not in [loc.lower() for loc in allowed_locations]
                ):
                    violations.append(
                        {
                            "policy": display_name,
                            "type": "location_restriction",
                            "message": f"Location '{location}' is not in allowed locations: {', '.join(allowed_locations)}",
                            "remediation": f"Use one of these locations: {', '.join(allowed_locations)}",
                        }
                    )
                    logger.warning(
                        f"Policy violation detected: {display_name} - location not allowed"
                    )

            if (
                "require" in display_name.lower()
                and "tag" in display_name.lower()
                and include_warnings
            ):
                warnings.append(
                    {
                        "policy": display_name,
                        "type": "required_tags",
                        "message": f"Policy '{display_name}' may require specific tags",
                        "remediation": "Review policy requirements and ensure all required tags are present",
                    }
                )

            if (
                "allowed" in display_name.lower()
                and ("sku" in display_name.lower() or "size" in display_name.lower())
                and include_warnings
            ):
                warnings.append(
                    {
                        "policy": display_name,
                        "type": "sku_restriction",
                        "message": f"Policy '{display_name}' may restrict SKUs or sizes",
                        "remediation": "Review policy to ensure the SKU/size you're deploying is allowed",
                    }
                )

        except Exception as e:
            logger.error(f"Error evaluating policy assignment: {e}")
            continue

    if what_if_results:
        changes = what_if_results.get("changes", [])
        logger.debug(f"What-If detected {len(changes)} changes")

        error = what_if_results.get("error", {})
        if error:
            error_message = error.get("message", "Unknown error")
            if "policy" in error_message.lower():
                violations.append(
                    {
                        "policy": "What-If Error",
                        "type": "deployment_error",
                        "message": f"Deployment validation failed: {error_message}",
                        "remediation": "Review the error message and fix the issue before deploying",
                    }
                )

    logger.debug(f"Policy evaluation: {len(violations)} violations, {len(warnings)} warnings")

    return {"violations": violations, "warnings": warnings}


def format_violation_message(
    violations: list[dict[str, Any]], warnings: list[dict[str, Any]] | None = None
) -> str:
    """Format policy violations into user-friendly message.

    Args:
        violations: Policy violations
        warnings: Optional policy warnings

    Returns:
        Formatted message
    """
    message_parts = []

    # Format violations
    if violations:
        message_parts.append(f"**{len(violations)} Policy Violation(s) Detected:**\n")
        for i, violation in enumerate(violations, 1):
            policy_name = violation.get("policy", "Unknown Policy")
            violation_type = violation.get("type", "unknown")
            violation_msg = violation.get("message", "")
            remediation = violation.get("remediation", "")

            message_parts.append(f"{i}. **{policy_name}** ({violation_type})")
            message_parts.append(f"   - {violation_msg}")
            if remediation:
                message_parts.append(f"   - 💡 **Fix**: {remediation}")
            message_parts.append("")

    # Format warnings
    if warnings:
        message_parts.append(f"\n**{len(warnings)} Policy Warning(s):**\n")
        for i, warning in enumerate(warnings, 1):
            policy_name = warning.get("policy", "Unknown Policy")
            warning_msg = warning.get("message", "")

            message_parts.append(f"{i}. {policy_name}")
            message_parts.append(f"   - ⚠️ {warning_msg}")
            message_parts.append("")

    return "\n".join(message_parts)
