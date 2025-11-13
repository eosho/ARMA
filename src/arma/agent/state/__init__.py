"""State schema exports for the deployment agent.

This module exports the main ARMAAgentState and all supporting type definitions
for easy importing throughout the codebase.

Example:
    >>> from arma.agent.state import ARMAAgentState, ValidationResultsDict, DeploymentStatus
    >>> state = ARMAAgentState(messages=[], thread_id="123")
"""

from arma.agent.state.azure import (
    AzureContextDict,
    DeploymentScope,
    TemplateInfoDict,
    TemplateParameterDict,
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
from arma.agent.state.schema import (
    ARMAAgentState,
    Intent,
    UserRole,
)
from arma.agent.state.validation import (
    ResourceValidationDict,
    ValidationResultsDict,
)

__all__ = [
    # Main state
    "ARMAAgentState",
    "Intent",
    "UserRole",
    # Azure types
    "AzureContextDict",
    "DeploymentScope",
    "TemplateInfoDict",
    "TemplateParameterDict",
    # Execution types
    "ApprovalDecisionDict",
    "ApprovalStatus",
    "DeploymentStatus",
    "ErrorInfoDict",
    # Planning types
    "DeploymentPlanDict",
    "WhatIfResultsDict",
    # Validation types
    "ResourceValidationDict",
    "ValidationResultsDict",
]
