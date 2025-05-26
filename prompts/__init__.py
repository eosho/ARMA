"""
This module contains the prompts for the agents.
"""
from .arma import ARMA_SUPERVISOR_PROMPT
from .intent_agent import INTENT_EXTRACTION_SYSTEM_PROMPT
from .resource_action_agent import RESOURCE_ACTION_SYSTEM_PROMPT
from .validation_agent import VALIDATION_SYSTEM_PROMPT
from .deployment_agent import DEPLOYMENT_SYSTEM_PROMPT

__all__ = [
    "ARMA_SUPERVISOR_PROMPT",
    "INTENT_EXTRACTION_SYSTEM_PROMPT",
    "RESOURCE_ACTION_SYSTEM_PROMPT",
    "VALIDATION_SYSTEM_PROMPT",
    "DEPLOYMENT_SYSTEM_PROMPT"
]
