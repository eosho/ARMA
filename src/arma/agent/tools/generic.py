"""Generic tools for the agent."""

from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

from ... import __version__


@tool(description="Return the current date/time in a given timezone")
def get_current_date(
    tz: str = "America/New_York",
    kind: str = "date",  # "date" | "datetime" | "iso"
) -> str:
    """Return the current date/time in a given timezone.

    Args:
        tz: IANA timezone (e.g., "UTC", "America/New_York").
        kind: "date" -> YYYY-MM-DD
              "datetime" -> YYYY-MM-DD HH:MM:SS
              "iso" -> ISO 8601 with timezone

    Returns:
        Formatted date/time string.

    Raises:
        ValueError: If timezone is invalid or kind is unsupported.
    """
    try:
        now = datetime.now(ZoneInfo(tz))
    except Exception as exc:
        raise ValueError(f"Invalid timezone: {tz!r}") from exc

    if kind == "date":
        return now.strftime("%Y-%m-%d")
    if kind == "datetime":
        return now.strftime("%Y-%m-%d %H:%M:%S")
    if kind == "iso":
        return now.isoformat()

    raise ValueError("kind must be one of: 'date', 'datetime', 'iso'")


@tool(description="Return the version of ARMA")
def get_arma_version() -> str:
    """Return the version of ARMA (Azure Resource Management Assistant)."""
    return __version__
