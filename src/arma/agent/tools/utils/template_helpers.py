"""Template discovery utilities for finding Bicep templates and validating parameters."""

from pathlib import Path
from typing import Any

from arma.core.logging import get_logger

logger = get_logger(__name__)

# Base path for Bicep modules - go up to project root
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
                line = line.strip()
                if line.startswith("param "):
                    line_content = line[6:].strip()

                    if "=" in line_content:
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
    scope = "resourceGroup"

    try:
        with open(template_path) as f:
            for line in f:
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
                    break

    except Exception as e:
        logger.error(f"Error reading template scope from {template_path}: {e}")

    return scope


def validate_template_parameters(
    template_path: str, provided_parameters: dict[str, Any]
) -> dict[str, Any]:
    """Validate provided parameters against template parameter definitions.

    Checks for:
    - Missing required parameters
    - Type mismatches between provided values and expected types
    - Extra parameters not defined in template

    Args:
        template_path: Path to the Bicep template file.
        provided_parameters: Dictionary of parameter names and values to validate.

    Returns:
        Dictionary with validation results:
        {
            'valid': bool,
            'errors': list[str],
            'warnings': list[str],
            'missing_required': list[str],
            'type_mismatches': list[dict],
            'extra_parameters': list[str]
        }

    Examples:
        >>> params = {'storageAccountName': 'mystore', 'sku': 123}
        >>> result = validate_template_parameters('/path/to/main.bicep', params)
        >>> print(result)
        {
            'valid': False,
            'errors': ['Missing required parameter: location'],
            'warnings': [],
            'missing_required': ['location'],
            'type_mismatches': [{'name': 'sku', 'expected': 'string', 'got': 'int'}],
            'extra_parameters': []
        }
    """
    result = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "missing_required": [],
        "type_mismatches": [],
        "extra_parameters": [],
    }

    # Get template parameter definitions
    template_params = get_template_parameters(template_path)
    if not template_params:
        logger.warning(f"No parameters found in template: {template_path}")
        return result

    # Create lookup dict for template params
    template_params_dict = {p["name"]: p for p in template_params}

    # Check for missing required parameters
    for param in template_params:
        if param.get("required", False) and param["name"] not in provided_parameters:
            result["missing_required"].append(param["name"])
            result["errors"].append(f"Missing required parameter: {param['name']}")
            result["valid"] = False

    # Check for type mismatches and extra parameters
    for param_name, param_value in provided_parameters.items():
        if param_name not in template_params_dict:
            result["extra_parameters"].append(param_name)
            result["warnings"].append(
                f"Parameter '{param_name}' not defined in template (will be ignored)"
            )
            continue

        template_param = template_params_dict[param_name]
        expected_type = template_param["type"]
        actual_type = _get_bicep_type(param_value)

        if not _is_type_compatible(expected_type, actual_type, param_value):
            mismatch = {
                "name": param_name,
                "expected": expected_type,
                "got": actual_type,
                "value": param_value,
            }
            result["type_mismatches"].append(mismatch)
            result["errors"].append(
                f"Type mismatch for '{param_name}': expected {expected_type}, got {actual_type} (value: {param_value})"
            )
            result["valid"] = False

    return result


def _get_bicep_type(value: Any) -> str:
    """Map Python type to Bicep type string."""
    if isinstance(value, bool):
        return "bool"
    elif isinstance(value, int):
        return "int"
    elif isinstance(value, str):
        return "string"
    elif isinstance(value, list):
        return "array"
    elif isinstance(value, dict):
        return "object"
    else:
        return "unknown"


def _is_type_compatible(expected: str, actual: str, value: Any) -> bool:
    """Check if actual type is compatible with expected Bicep type.

    Handles some common type conversions:
    - int can be used for string (will be converted)
    - string numbers can be used for int (if parseable)
    """
    if expected == actual:
        return True

    # Allow int to be passed as string (Bicep will convert)
    if expected == "string" and actual == "int":
        return True

    # Allow string numbers to be passed as int (if valid)
    if expected == "int" and actual == "string":
        try:
            int(value)
            return True
        except (ValueError, TypeError):
            return False

    return False
