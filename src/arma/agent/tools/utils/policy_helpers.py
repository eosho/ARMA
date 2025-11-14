"""Policy compliance helper utilities for Azure Policy validation.

This module provides utilities to check Azure Policy compliance before deployments:
- Get policy assignments for a scope
- Evaluate policy compliance against assignments
- Format violation messages
"""

import json
import subprocess
from typing import Any

from arma.core.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Azure Policy Client - API interactions
# =============================================================================


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


# =============================================================================
# Policy Evaluator - Compliance checking logic
# =============================================================================


def trigger_policy_scan(
    subscription_id: str,
    resource_group: str | None = None,
) -> dict[str, Any] | None:
    """Trigger on-demand policy compliance scan.

    Args:
        subscription_id: Azure subscription ID
        resource_group: Optional resource group name

    Returns:
        Scan trigger response or None if failed
    """
    try:
        scope = f"/subscriptions/{subscription_id}"
        if resource_group:
            scope = f"{scope}/resourceGroups/{resource_group}"

        cmd = [
            "az",
            "rest",
            "--method",
            "POST",
            "--url",
            f"https://management.azure.com{scope}/providers/Microsoft.PolicyInsights/policyStates/latest/triggerEvaluation?api-version=2019-10-01",
        ]

        logger.debug(f"Triggering policy scan for scope: {scope}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0 or result.returncode == 202:
            logger.debug("Policy scan triggered successfully")
            return {"status": "triggered", "scope": scope}
        else:
            logger.warning(f"Failed to trigger policy scan: {result.stderr}")
            return None

    except subprocess.TimeoutExpired:
        logger.error("Policy scan trigger timed out")
        return None
    except Exception as e:
        logger.error(f"Error triggering policy scan: {e}")
        return None


def get_policy_states(
    subscription_id: str,
    resource_group: str | None = None,
    resource_type: str | None = None,
) -> list[dict[str, Any]]:
    """Get latest policy compliance states for a scope.

    Args:
        subscription_id: Azure subscription ID
        resource_group: Optional resource group name
        resource_type: Optional resource type filter

    Returns:
        List of policy state records
    """
    try:
        cmd = [
            "az",
            "policy",
            "state",
            "list",
            "--subscription",
            subscription_id,
            "-o",
            "json",
        ]

        # Add resource group filter if provided
        if resource_group:
            cmd.extend(["--resource-group", resource_group])

        # Add resource type filter if provided
        if resource_type:
            cmd.extend(["--filter", f"resourceType eq '{resource_type}'"])

        logger.debug(f"Fetching policy states for subscription: {subscription_id}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode == 0:
            states = json.loads(result.stdout)
            logger.debug(f"Retrieved {len(states)} policy state records")
            return states
        else:
            logger.error(f"Failed to get policy states: {result.stderr}")
            return []

    except subprocess.TimeoutExpired:
        logger.error("Policy states query timed out")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse policy states JSON: {e}")
        return []
    except Exception as e:
        logger.error(f"Error getting policy states: {e}")
        return []


def evaluate_policy_compliance(
    subscription_id: str,
    resource_group: str | None = None,
    resource_type: str | None = None,
    include_warnings: bool = True,
) -> dict[str, Any]:
    """Evaluate policy compliance using Azure Policy Insights API.

    This triggers an on-demand scan and queries the latest policy states,
    similar to the Azure/policy-compliance-scan GitHub Action.

    Args:
        subscription_id: Azure subscription ID
        resource_group: Optional resource group name
        resource_type: Optional resource type filter
        include_warnings: Include Audit policy warnings

    Returns:
        Dict with 'violations' and 'warnings' lists
    """
    violations = []
    warnings = []

    logger.debug(f"Evaluating compliance for subscription: {subscription_id}")

    # Trigger on-demand scan (best effort - may not complete immediately)
    trigger_result = trigger_policy_scan(subscription_id, resource_group)
    if trigger_result:
        logger.debug("On-demand policy scan triggered")

    # Get latest policy states
    policy_states = get_policy_states(subscription_id, resource_group, resource_type)

    if not policy_states:
        logger.warning("No policy states found - resources may not exist yet or scan not complete")
        return {"violations": violations, "warnings": warnings}

    # Process policy states
    for state in policy_states:
        try:
            compliance_state = state.get("complianceState", "")
            policy_name = state.get("policyDefinitionName", "Unknown Policy")
            policy_assignment_name = state.get("policyAssignmentName", "")
            resource_id = state.get("resourceId", "")
            policy_definition_action = state.get("policyDefinitionAction", "")

            # Skip compliant resources
            if compliance_state == "Compliant":
                continue

            # Build violation/warning record
            record = {
                "policy": policy_assignment_name or policy_name,
                "resource": resource_id.split("/")[-1] if resource_id else "Unknown",
                "type": policy_definition_action or "policy_violation",
                "message": f"Resource is {compliance_state} with policy '{policy_assignment_name or policy_name}'",
                "remediation": "Review policy requirements and update resource configuration",
                "compliance_state": compliance_state,
            }

            # Categorize based on policy effect and compliance state
            if compliance_state == "NonCompliant":
                if policy_definition_action.lower() in ["deny", "deployifnotexists"]:
                    violations.append(record)
                    logger.warning(f"Policy violation: {policy_assignment_name}")
                elif include_warnings:
                    warnings.append(record)
                    logger.debug(f"Policy warning: {policy_assignment_name}")
            elif compliance_state in ["Unknown", "Conflict"] and include_warnings:
                warnings.append(record)

        except Exception as e:
            logger.error(f"Error processing policy state: {e}")
            continue

    logger.debug(f"Policy evaluation: {len(violations)} violations, {len(warnings)} warnings")
    return {"violations": violations, "warnings": warnings}


# =============================================================================
# Message Formatter - User-friendly output
# =============================================================================


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
