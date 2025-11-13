"""Bicep compilation utilities."""

import json
import subprocess
from pathlib import Path
from typing import Any

from arma.core.logging import get_logger

logger = get_logger(__name__)


async def compile_bicep_to_arm(template_path: str) -> Any:
    """Compile Bicep template to ARM JSON.

    Args:
        template_path: Path to Bicep template file.

    Returns:
        Compiled ARM template as dictionary.

    Raises:
        FileNotFoundError: If template file doesn't exist.
        subprocess.CalledProcessError: If compilation fails.
    """
    # Check if template exists
    template_file = Path(template_path)
    if not template_file.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    # If already ARM JSON, load directly
    if template_path.endswith(".json"):
        logger.debug(f"Loading ARM template directly: {template_path}")
        with open(template_path) as f:
            return json.load(f)

    # Compile Bicep to ARM using Azure CLI
    logger.debug(f"Compiling Bicep template: {template_path}")
    result = subprocess.run(
        ["az", "bicep", "build", "--file", template_path, "--stdout"],
        capture_output=True,
        text=True,
        check=True,
    )

    return json.loads(result.stdout)
