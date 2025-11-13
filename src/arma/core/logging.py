"""Logging configuration for ARMA.

This module provides structured logging with JSON formatting for production
and human-readable formatting for development.
"""

import logging
import sys
from typing import Any


def setup_logging() -> None:
    """Configure application-wide logging.

    Sets up structured logging with appropriate formatters based on environment.
    Call this once at application startup.
    """
    log_level = logging.INFO

    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Human-readable formatter for development
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Suppress noisy loggers
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given name.

    Args:
        name: Logger name (typically __name__ of the calling module)

    Returns:
        Logger instance configured with application settings

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing deployment")
    """
    return logging.getLogger(name)


class LoggerAdapter(logging.LoggerAdapter):
    """Logger adapter for adding contextual information.

    This adapter allows adding extra context (like request ID, user ID)
    to all log messages from a specific logger instance.

    Example:
        >>> logger = get_logger(__name__)
        >>> adapter = LoggerAdapter(logger, {"request_id": "abc123", "user_id": "user@example.com"})
        >>> adapter.info("Deployment started")
        # Output: ... | request_id=abc123 user_id=user@example.com | Deployment started
    """

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        """Process log message with extra context.

        Args:
            msg: Log message
            kwargs: Log kwargs

        Returns:
            Tuple of (modified_msg, kwargs)
        """
        # Add extra context to message
        if self.extra:
            context = " ".join(f"{k}={v}" for k, v in self.extra.items())
            msg = f"{context} | {msg}"
        return msg, kwargs


# Initialize logging on module import
setup_logging()
