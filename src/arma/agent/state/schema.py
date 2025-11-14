"""Consolidated ARMA Agent State Schema.

This module defines the complete ARMAAgentState that extends LangChain's AgentState
with all fields needed for Azure deployment operations.
"""

from typing import Any, Literal, NotRequired

from langchain.agents import AgentState

# Type aliases
DeploymentScope = Literal["resourceGroup", "subscription", "managementGroup", "tenant"]
DeploymentStatus = Literal[
    "pending",
    "analyzing",
    "planning",
    "awaiting_approval",
    "executing",
    "completed",
    "failed",
    "cancelled",
]
ApprovalStatus = Literal["pending", "approved", "rejected", "edited"]
Intent = Literal["deploy", "update", "delete", "query", "unknown"]
UserRole = Literal["admin", "contributor", "reader", "guest"]


class ARMAAgentState(AgentState):
    """Complete agent state for ARMA deployment operations.

    Extends LangChain AgentState with Azure deployment-specific fields.
    All fields are optional (NotRequired) to support incremental state building.

    Fields are organized by category:
    - Azure Context: subscription, resource group, location, etc.
    - Template Discovery: template path, parameters, scope
    - Deployment Planning: deployment plan, what-if results
    - Execution: deployment status, approval decisions
    - Validation: resource validation, policy compliance
    - Usage Tracking: token counts, model calls
    - Query Results: resource lists, resource details
    """

    # ===== Azure Context (set by PreflightMiddleware) =====
    subscription_id: NotRequired[str]
    """Azure subscription GUID."""

    subscription_name: NotRequired[str]
    """Human-readable subscription name."""

    tenant_id: NotRequired[str]
    """Azure AD tenant GUID."""

    resource_group: NotRequired[str]
    """Target resource group name."""

    location: NotRequired[str]
    """Azure region (e.g., 'eastus', 'westus2')."""

    tags: NotRequired[dict[str, str]]
    """Resource tags to apply."""

    user_roles: NotRequired[list[str]]
    """User's Azure roles for the subscription (e.g., ['Contributor', 'Owner'])."""

    resource_group_exists: NotRequired[bool]
    """Whether the resource group exists in Azure."""

    resource_group_accessible: NotRequired[bool]
    """Whether user has deployment permissions for the resource group."""

    resource_group_checked: NotRequired[bool]
    """Whether resource group existence has been checked."""

    # ===== Resource Context (set by PreflightMiddleware tools) =====
    resource_name: NotRequired[str]
    """Target resource name."""

    resource_type: NotRequired[str]
    """Azure resource type (e.g., 'Microsoft.Storage/storageAccounts')."""

    resource_exists: NotRequired[bool]
    """Whether the resource already exists."""

    intent: NotRequired[Intent]
    """Deployment intent: deploy, update, delete, query."""

    # ===== Template Discovery (set by TemplateDiscoveryMiddleware) =====
    template_path: NotRequired[str]
    """Absolute path to Bicep template file."""

    template_discovery_status: NotRequired[str]
    """Status: 'success', 'failed', 'not_attempted'."""

    template_discovery_error: NotRequired[str]
    """Error message if discovery failed."""

    deployment_scope: NotRequired[DeploymentScope]
    """Deployment scope from Bicep targetScope."""

    template_parameters: NotRequired[list[dict[str, Any]]]
    """List of parameter definitions from template."""

    template_resources: NotRequired[list[dict[str, Any]]]
    """List of resources defined in template."""

    # ===== Deployment Planning (set by plan_deployment tool) =====
    deployment_plan: NotRequired[dict[str, Any]]
    """Complete deployment plan with ARM template, parameters, what-if results.

    Structure:
        - summary: str
        - deployment_name: str
        - template_path: str
        - deployment_scope: DeploymentScope
        - subscription_id: str
        - resource_group: str | None
        - location: str
        - parameters: dict[str, Any]
        - resources: list[dict[str, Any]]
        - what_if_results: dict[str, Any]
        - arm_template: dict[str, Any]
        - created_at: str (ISO 8601)
        - created_by: str
    """

    parameters: NotRequired[dict[str, Any]]
    """User-provided + default parameters for deployment."""

    what_if_results: NotRequired[dict[str, Any]]
    """Azure What-If analysis results showing predicted changes."""

    # ===== Policy Compliance (set by AzurePolicyComplianceMiddleware) =====
    policy_check_status: NotRequired[str]
    """Status: 'completed', 'skipped', 'error'."""

    policy_violations: NotRequired[list[dict[str, Any]]]
    """List of Deny policy violations that block deployment."""

    policy_warnings: NotRequired[list[dict[str, Any]]]
    """List of Audit policy warnings (informational)."""

    # ===== Deployment Execution (set by execute_deployment tool) =====
    deployment_status: NotRequired[DeploymentStatus]
    """Current deployment execution status."""

    deployment_name: NotRequired[str]
    """Azure deployment name."""

    deployment_id: NotRequired[str]
    """Azure deployment resource ID."""

    deployment_result: NotRequired[dict[str, Any]]
    """Deployment operation result from Azure."""

    deployment_outputs: NotRequired[dict[str, Any]]
    """ARM template outputs after successful deployment."""

    deployment_error: NotRequired[str]
    """Error message if deployment failed."""

    deployed_resources: NotRequired[list[dict[str, Any]]]
    """List of successfully deployed resources with IDs."""

    # ===== HITL Approval (set by HumanInTheLoopMiddleware) =====
    approval_status: NotRequired[ApprovalStatus]
    """Current approval status."""

    approval_decisions: NotRequired[list[dict[str, Any]]]
    """History of approval decisions."""

    # ===== Validation (set by validation tools) =====
    validation_results: NotRequired[dict[str, Any]]
    """Overall validation results."""

    validation_errors: NotRequired[list[str]]
    """List of validation errors."""

    validation_warnings: NotRequired[list[str]]
    """List of validation warnings."""

    # ===== Query Results (set by query tools) =====
    query_results: NotRequired[list[dict[str, Any]]]
    """Results from list_resources or other query operations."""

    last_query: NotRequired[str]
    """Last executed query for debugging."""

    resource_details: NotRequired[dict[str, Any]]
    """Detailed resource information from get_resource."""

    # ===== Usage Tracking (set by UsageTrackingMiddleware) =====
    total_input_tokens: NotRequired[int]
    """Total input tokens consumed."""

    total_output_tokens: NotRequired[int]
    """Total output tokens produced."""

    total_tokens: NotRequired[int]
    """Total tokens processed."""

    total_calls: NotRequired[int]
    """Total model calls made."""

    # ===== User Context (set by CLI or API) =====
    user_id: NotRequired[str]
    """User identifier for tagging and audit."""

    user_role: NotRequired[UserRole]
    """User's role for authorization."""

    session_id: NotRequired[str]
    """Session identifier for tracking."""

    # ===== Error Tracking =====
    last_error: NotRequired[dict[str, Any]]
    """Last error encountered with type, message, traceback."""

    retry_count: NotRequired[int]
    """Number of retry attempts for current operation."""
