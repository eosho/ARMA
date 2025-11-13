"""Deployment tools for the Azure deployment agent."""

from arma.agent.tools.execute import execute_deployment
from arma.agent.tools.generic import get_arma_version, get_current_date
from arma.agent.tools.plan import plan_deployment, preview_what_if
from arma.agent.tools.query import (
    delete_resource,
    get_resource,
    list_resources,
    update_resource_tags,
)

__all__ = [
    "plan_deployment",
    "preview_what_if",
    "execute_deployment",
    "list_resources",
    "get_arma_version",
    "get_current_date",
    "get_resource",
    "delete_resource",
    "update_resource_tags",
]
