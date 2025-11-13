"""Deployment agent state schema.

This module defines the main ARMAAgentState that extends LangChain's AgentState
with comprehensive fields for Azure deployment workflows.

TOOL-TO-STATE MAPPING:
- ValidationMiddleware: subscription_id, resource_group, location
- check_existing_resource: intent, existing_resources
- TemplateDiscoveryMiddleware: template_path, template_info, deployment_scope
- plan_deployment: deployment_plan, what_if_results, parameters
- execute_deployment: deployment_status, deployment_id, deployment_outputs
- list_resources: query_results, last_query
- get_resource: selected_resource
- delete_resource: (reads resource_id from args, no state writes)
"""

from datetime import datetime
from typing import Any, Literal, NotRequired

from langchain.agents import AgentState

from arma.agent.state.azure import (
    DeploymentScope,
    TemplateInfoDict,
)
from arma.agent.state.execution import (
    ApprovalDecisionDict,
    ApprovalStatus,
    DeploymentStatus,
    ErrorInfoDict,
)
from arma.agent.state.planning import (
    DeploymentPlanDict,
    WhatIfResultsDict,
)
from arma.agent.state.validation import (
    ResourceValidationDict,
    ValidationResultsDict,
)

Intent = Literal["deploy", "update", "delete", "query", "chat"]
UserRole = Literal["admin", "approver", "deployer", "viewer"]


class ARMAAgentState(AgentState):
    """Extended agent state for Azure deployment workflows.

    Extends LangChain's AgentState (provides 'messages' field) with Azure-specific
    fields for validation, planning, execution, and HITL approval.
    """

    # === Core Identification ===
    thread_id: NotRequired[str]
    """LangGraph conversation thread ID for state persistence."""

    user_id: NotRequired[str]
    """Authenticated user identifier (email or username)."""

    deployment_id: NotRequired[str]
    """Unique deployment identifier (UUID)."""

    # === Intent & Request ===
    intent: NotRequired[Intent]
    """User's intent: deploy, update, delete, query, or chat."""

    original_request: NotRequired[str]
    """User's original natural language request."""

    # === Azure Deployment Context ===
    subscription_id: NotRequired[str]
    """Target Azure subscription GUID."""

    resource_group: NotRequired[str]
    """Target resource group name."""

    location: NotRequired[str]
    """Target Azure region."""

    deployment_scope: NotRequired[DeploymentScope]
    """Deployment scope: resourceGroup, subscription, managementGroup, or tenant."""

    tags: NotRequired[dict[str, str]]
    """Azure resource tags to apply."""

    # === Resource Information ===
    resource_type: NotRequired[str]
    """Primary Azure resource type."""

    resource_names: NotRequired[list[str]]
    """Names of resources being created/modified."""

    existing_resources: NotRequired[list[dict[str, Any]]]
    """Existing Azure resources found during validation."""

    # === Template Information ===
    template_path: NotRequired[str]
    """Absolute path to Bicep/ARM template file."""

    template_info: NotRequired[TemplateInfoDict]
    """Template metadata including parameters and resource types."""

    parameters: NotRequired[dict[str, Any]]
    """Template parameter values (merged: user-provided + defaults)."""

    template_discovery_status: NotRequired[str]
    """Status of template discovery."""

    template_discovery_error: NotRequired[str]
    """Error message if template discovery failed."""

    # === Query Results ===
    query_results: NotRequired[list[dict[str, Any]]]
    """Results from list_resources tool (list of Azure resources)."""

    last_query: NotRequired[dict[str, Any]]
    """Metadata about the last query executed (resource_type, location, resource_group, count)."""

    selected_resource: NotRequired[dict[str, Any]]
    """Resource details from get_resource tool."""

    # === Validation Results ===
    validation_results: NotRequired[ValidationResultsDict]
    """Overall validation results."""

    missing_parameters: NotRequired[list[str]]
    """List of required parameters that are missing values."""

    resource_validation: NotRequired[ResourceValidationDict]
    """Resource naming and convention validation results."""

    # === Planning ===
    deployment_plan: NotRequired[DeploymentPlanDict]
    """Generated deployment plan."""

    what_if_results: NotRequired[WhatIfResultsDict]
    """Azure what-if deployment preview results."""

    # === Policy Compliance ===
    policy_check_status: NotRequired[str]
    """Status of policy compliance check: completed, error, or skipped."""

    policy_violations: NotRequired[list[dict[str, Any]]]
    """List of Azure Policy violations that would block deployment."""

    policy_warnings: NotRequired[list[dict[str, Any]]]
    """List of Azure Policy warnings (Audit policies)."""

    # === Execution ===
    deployment_status: NotRequired[DeploymentStatus]
    """Current deployment execution status."""

    execution_start_time: NotRequired[datetime]
    """Timestamp when deployment execution started."""

    execution_end_time: NotRequired[datetime]
    """Timestamp when deployment execution completed."""

    deployment_outputs: NotRequired[dict[str, Any]]
    """ARM deployment outputs."""

    deployment_errors: NotRequired[list[str]]
    """List of errors encountered during deployment."""

    # === HITL Approval ===
    approval_status: NotRequired[ApprovalStatus]
    """Current HITL approval status."""

    approval_feedback: NotRequired[str]
    """User feedback provided with approval decision."""

    approval_decisions: NotRequired[list[ApprovalDecisionDict]]
    """History of approval decisions for tool calls."""

    approver_id: NotRequired[str]
    """User who approved/rejected the deployment."""

    # === Error Handling ===
    last_error: NotRequired[ErrorInfoDict]
    """Most recent error encountered."""

    retry_count: NotRequired[int]
    """Number of retry attempts for current operation."""

    error_stack: NotRequired[list[ErrorInfoDict]]
    """History of all errors in this session."""

    # === Feature Flags ===
    skip_validation: NotRequired[bool]
    """Whether to skip certain validation steps."""

    # === Conversation Management ===
    conversation_turn: NotRequired[int]
    """Current conversation turn number."""

    session_start_time: NotRequired[datetime]
    """When the conversation session started."""

    # === User Context ===
    user_role: NotRequired[UserRole]
    """User's role: admin, approver, deployer, or viewer."""

    user_preferences: NotRequired[dict[str, Any]]
    """User preferences for UI and behavior."""

    # === Telemetry ===
    llm_calls: NotRequired[int]
    """Count of LLM API calls in this session."""

    tool_calls: NotRequired[int]
    """Count of tool invocations in this session."""

    api_calls: NotRequired[int]
    """Count of Azure API calls in this session."""
