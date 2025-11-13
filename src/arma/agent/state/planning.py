"""Planning and what-if result types.

This module contains TypedDict definitions for deployment planning and what-if results.

Set by: plan_deployment tool
Used by: execute_deployment tool, Agent for displaying plans
"""

from typing import Any, Literal, TypedDict


class WhatIfResultsDict(TypedDict, total=False):
    """Azure what-if deployment preview results.

    Set by: plan_deployment tool (via run_what_if_deployment)
    Used by: Agent to display predicted changes to user
    """

    status: str
    """Overall what-if operation status: 'Succeeded' or 'Failed'."""

    error: str
    """Error message if what-if failed (only when status='Failed')."""

    changes: list[dict[str, Any]]
    """List of predicted resource changes (create/modify/delete/nochange)."""

    resources_created: int
    """Count of resources to be created."""

    resources_modified: int
    """Count of resources to be modified."""

    resources_deleted: int
    """Count of resources to be deleted."""

    resources_no_change: int
    """Count of resources with no changes."""

    total_resources: int
    """Total resources in deployment."""


class DeploymentPlanDict(TypedDict, total=False):
    """Complete deployment plan with all information needed for execution.

    Set by: plan_deployment tool
    Required by: execute_deployment tool (MUST be present to execute)
    Used by: Agent for displaying plan, HITL for approval
    """

    summary: str
    """Human-readable deployment summary (e.g., 'Deploy 1 storage account to eastus')."""

    deployment_name: str
    """Unique name for Azure deployment (e.g., 'arma-deploy-20240115-143022')."""

    template_path: str
    """Absolute path to Bicep template file."""

    deployment_scope: Literal["resourceGroup", "subscription", "managementGroup", "tenant"]
    """Deployment scope level."""

    subscription_id: str
    """Target Azure subscription GUID."""

    resource_group: str | None
    """Target resource group (None for subscription/managementGroup/tenant scope)."""

    location: str
    """Resource group location or deployment location."""

    parameters: dict[str, Any]
    """Merged template parameters (user-provided + defaults)."""

    resources: list[dict[str, Any]]
    """List of resources to be deployed with names, types, properties."""

    what_if_results: WhatIfResultsDict
    """Predicted deployment changes from Azure what-if API."""

    arm_template: dict[str, Any]
    """Compiled ARM template JSON (from compile_bicep_to_arm)."""

    created_at: str
    """ISO 8601 timestamp when plan was generated."""

    created_by: str
    """User who created the plan."""
