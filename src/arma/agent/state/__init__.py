"""State schema exports for the deployment agent.

This module exports the main ARMAAgentState and all supporting type definitions
for easy importing throughout the codebase.

Example:
    >>> from arma.agent.state import ARMAAgentState, DeploymentScope, DeploymentStatus
    >>> state = ARMAAgentState(messages=[], thread_id="123")
"""

from arma.agent.state.schema import (
    ApprovalStatus,
    ARMAAgentState,
    DeploymentScope,
    DeploymentStatus,
    Intent,
    UserRole,
)

__all__ = [
    "ARMAAgentState",
    "ApprovalStatus",
    "DeploymentScope",
    "DeploymentStatus",
    "Intent",
    "UserRole",
]
