"""Version info for the barbershop booking agent.

Reads version from pyproject.toml so there's a single source of truth.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def get_version() -> str:
    """Return version string from pyproject.toml (e.g., '0.1.1')."""

    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data: dict[str, object] = tomllib.load(f)

    project = data.get("project")
    if not isinstance(project, dict):
        raise KeyError("Missing [project] table in pyproject.toml")

    version = project.get("version")
    if not isinstance(version, str):
        raise KeyError("Missing or invalid 'version' in [project]")

    return version


__version__ = get_version()
