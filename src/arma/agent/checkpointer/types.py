"""Type definitions for checkpointer factory."""

from typing import TypedDict


class CheckpointConfig(TypedDict, total=False):
    """Configuration for checkpointer creation."""

    thread_id: str  # Optional default thread ID
    """Thread ID to use for checkpointer."""

    user_id: str  # Optional default user ID
    """User ID to use for checkpointer."""
