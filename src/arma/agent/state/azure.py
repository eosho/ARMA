"""Azure-specific type definitions for deployment state.

This module defines TypedDicts for Azure-related state fields including
deployment context, template information, and deployment scope.

Set by: ValidationMiddleware, TemplateDiscoveryMiddleware
Used by: All Azure tools (plan, execute, list, get, delete)
"""

from typing import Any, Literal, TypedDict

DeploymentScope = Literal["resourceGroup", "subscription", "managementGroup", "tenant"]
"""Azure deployment scope levels.

- resourceGroup: Deploy to a resource group (most common)
- subscription: Deploy at subscription level
- managementGroup: Deploy at management group level
- tenant: Deploy at tenant root level

Set by: TemplateDiscoveryMiddleware (from Bicep targetScope directive)
Default: "resourceGroup"
"""


class AzureContextDict(TypedDict, total=False):
    """Azure deployment context information.

    Set by: ValidationMiddleware.before_agent
    Used by: All Azure tools
    """

    subscription_id: str
    """Azure subscription GUID (e.g., 'e98a7bdd-1e97-452c-939c-4edf569d31f6')."""

    subscription_name: str
    """Human-readable subscription name (from Azure CLI)."""

    resource_group: str
    """Target resource group name (e.g., 'my-resource-group')."""

    location: str
    """Azure region (e.g., 'eastus', 'westus2', 'northeurope')."""

    tenant_id: str
    """Azure AD tenant GUID (from Azure CLI)."""

    tags: dict[str, str]
    """Resource tags to apply (e.g., {'environment': 'prod', 'owner': 'team'})."""


class TemplateParameterDict(TypedDict, total=False):
    """Single Bicep/ARM template parameter definition.

    Extracted by: TemplateDiscoveryMiddleware from Bicep file
    Used by: plan_deployment for parameter merging
    """

    name: str
    """Parameter name (e.g., 'storageAccountName', 'sku')."""

    type: str
    """Bicep type: 'string', 'int', 'bool', 'object', 'array', 'secureString'."""

    required: bool
    """Whether parameter must be provided by user."""

    default_value: Any
    """Default value if not provided by user."""

    description: str
    """Human-readable parameter description (from @description() decorator)."""

    allowed_values: list[Any]
    """List of valid values (from @allowed() decorator)."""

    min_length: int
    """Minimum string length (from @minLength() decorator)."""

    max_length: int
    """Maximum string length (from @maxLength() decorator)."""

    min_value: int
    """Minimum numeric value (from @minValue() decorator)."""

    max_value: int
    """Maximum numeric value (from @maxValue() decorator)."""


class TemplateInfoDict(TypedDict, total=False):
    """Complete template metadata.

    Set by: TemplateDiscoveryMiddleware
    Used by: Agent for displaying template info, plan_deployment for validation
    """

    template_path: str
    """Absolute path to Bicep template file."""

    deployment_scope: DeploymentScope
    """Scope extracted from Bicep targetScope directive."""

    parameters: list[TemplateParameterDict]
    """List of parameter definitions."""

    resources: list[dict[str, Any]]
    """List of resources defined in template."""

    outputs: dict[str, Any]
    """ARM template outputs."""

    description: str
    """Template description from Bicep metadata."""

    version: str
    """Template version from Bicep metadata."""

    author: str
    """Template author from Bicep metadata."""
