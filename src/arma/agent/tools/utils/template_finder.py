"""Template discovery utilities for finding Bicep templates."""

from pathlib import Path
from typing import Any

from arma.core.logging import get_logger

logger = get_logger(__name__)

# Base path for Bicep modules - go up to project root
# From: src/arma/agent/tools/utils/template_finder.py
# To:   bicep/modules/
BICEP_MODULES_PATH = Path(__file__).parent.parent.parent.parent.parent.parent / "bicep" / "modules"


def find_template_for_resource_type(resource_type: str) -> str | None:
    """Find Bicep template path for a given Azure resource type.

    The template structure follows the convention:
    bicep/modules/{provider}/{resourceType}/main.bicep

    For example:
    - Microsoft.Storage/storageAccounts -> bicep/modules/Microsoft.Storage/storageAccounts/main.bicep
    - Microsoft.Compute/virtualMachines -> bicep/modules/Microsoft.Compute/virtualMachines/main.bicep

    Args:
        resource_type: Azure resource type (e.g., 'Microsoft.Storage/storageAccounts')

    Returns:
        Absolute path to the template file if found, None otherwise.

    Examples:
        >>> path = find_template_for_resource_type('Microsoft.Storage/storageAccounts')
        >>> print(path)
        '/home/groot/arma/bicep/modules/Microsoft.Storage/storageAccounts/main.bicep'
    """
    if not resource_type or "/" not in resource_type:
        logger.warning(f"Invalid resource type format: {resource_type}")
        return None

    # Split resource type into provider and resource
    # e.g., "Microsoft.Storage/storageAccounts" -> ["Microsoft.Storage", "storageAccounts"]
    parts = resource_type.split("/", 1)
    provider = parts[0]
    resource = parts[1]

    # Build template path
    template_path = BICEP_MODULES_PATH / provider / resource / "main.bicep"

    if template_path.exists():
        logger.debug(f"Found template for {resource_type}: {template_path}")
        return str(template_path.resolve())

    logger.warning(f"Template not found for {resource_type} at {template_path}")
    return None


def get_template_parameters(template_path: str) -> list[dict[str, Any]]:
    """Extract parameter names and defaults from a Bicep template.

    Args:
        template_path: Path to the Bicep template file.

    Returns:
        List of dictionaries with 'name', 'type', and optional 'default' value.

    Examples:
        >>> params = get_template_parameters('/path/to/main.bicep')
        >>> print(params)
        [
            {'name': 'storageAccountName', 'type': 'string', 'required': True},
            {'name': 'location', 'type': 'string', 'default': "resourceGroup().location", 'required': False},
            {'name': 'sku', 'type': 'string', 'default': 'Standard_LRS', 'required': False}
        ]
    """
    parameters = []

    try:
        with open(template_path) as f:
            for line in f:
                # Look for parameter declarations
                # Format: param <name> <type> = <default>
                # or: param <name> <type>
                line = line.strip()
                if line.startswith("param "):
                    # Remove 'param ' prefix
                    line_content = line[6:].strip()

                    # Check if there's a default value (contains '=')
                    if "=" in line_content:
                        # Split by '=' to get name/type and default
                        parts = line_content.split("=", 1)
                        name_type = parts[0].strip().split()
                        default_value = parts[1].strip().strip("'\"")

                        if len(name_type) >= 2:
                            param_name = name_type[0]
                            param_type = name_type[1]
                            parameters.append(
                                {
                                    "name": param_name,
                                    "type": param_type,
                                    "default": default_value,
                                    "required": False,
                                }
                            )
                    else:
                        # No default value
                        parts = line_content.split()
                        if len(parts) >= 2:
                            param_name = parts[0]
                            param_type = parts[1]
                            parameters.append(
                                {"name": param_name, "type": param_type, "required": True}
                            )

    except Exception as e:
        logger.error(f"Error reading template parameters from {template_path}: {e}")

    return parameters


def get_template_scope(template_path: str) -> str:
    """Extract deployment scope from a Bicep template.

    The targetScope directive in Bicep defines where the template can be deployed:
    - 'resourceGroup' (default if not specified)
    - 'subscription'
    - 'managementGroup'
    - 'tenant'

    Args:
        template_path: Path to the Bicep template file.

    Returns:
        Deployment scope string. Defaults to 'resourceGroup' if not specified.

    Examples:
        >>> scope = get_template_scope('/path/to/main.bicep')
        >>> print(scope)
        'resourceGroup'
    """
    scope = "resourceGroup"  # Default scope

    try:
        with open(template_path) as f:
            for line in f:
                # Look for targetScope directive
                # Format: targetScope = 'scopeName'
                line = line.strip()
                if line.startswith("targetScope"):
                    # Extract scope value
                    # e.g., "targetScope = 'subscription'" -> 'subscription'
                    if "=" in line:
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            scope_value = parts[1].strip().strip("'\"")
                            if scope_value in [
                                "resourceGroup",
                                "subscription",
                                "managementGroup",
                                "tenant",
                            ]:
                                scope = scope_value
                                logger.debug(f"Template scope detected: {scope}")
                    break  # targetScope must be first non-comment line

    except Exception as e:
        logger.error(f"Error reading template scope from {template_path}: {e}")

    return scope
