"""Execution-related type definitions for deployment state.

This module defines enums and TypedDicts for deployment execution status,
approval workflows, and error tracking.

Set by: execute_deployment tool, HumanInTheLoopMiddleware
Used by: Agent for status tracking, UI for displaying progress
"""

from typing import Literal, TypedDict

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
"""Deployment execution status.

- pending: Initial state, not started
- analyzing: Analyzing user request
- planning: Generating deployment plan
- awaiting_approval: Waiting for HITL approval
- executing: Deployment in progress
- completed: Deployment succeeded
- failed: Deployment failed
- cancelled: Deployment cancelled by user

Set by: execute_deployment tool
Used by: Agent for progress tracking, UI for status display
"""


ApprovalStatus = Literal["pending", "approved", "rejected", "edited"]
"""HITL approval status.

- pending: Awaiting user decision
- approved: User approved tool call
- rejected: User rejected tool call
- edited: User edited tool call parameters

Set by: HumanInTheLoopMiddleware
Used by: Agent flow control, audit logging
"""


class ApprovalDecisionDict(TypedDict, total=False):
    """Single HITL approval decision record.

    Set by: HumanInTheLoopMiddleware
    Used by: Audit trail, telemetry
    """

    tool_name: str
    """Name of tool that required approval."""

    decision: ApprovalStatus
    """Approval decision: approved, rejected, or edited."""

    timestamp: str
    """ISO 8601 timestamp of decision."""

    feedback: str
    """User feedback provided with decision."""

    original_args: dict
    """Original tool arguments before edit."""

    edited_args: dict
    """Tool arguments after user edit (only if decision='edited')."""


class ErrorInfoDict(TypedDict, total=False):
    """Error information for tracking failures.

    Set by: Any tool that encounters an error
    Used by: Error recovery, user messaging, debugging
    """

    error_type: str
    """Type of error (e.g., 'ValidationError', 'DeploymentError', 'AzureAPIError')."""

    message: str
    """Human-readable error message."""

    timestamp: str
    """ISO 8601 timestamp when error occurred."""

    tool_name: str
    """Name of tool that encountered the error."""

    traceback: str
    """Full Python traceback for debugging."""

    retry_count: int
    """Number of times this operation has been retried."""

    recoverable: bool
    """Whether the error is potentially recoverable with retry."""
