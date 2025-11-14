"""Utilities for managing checkpoint history."""

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver


def get_checkpoint_history(
    checkpointer: BaseCheckpointSaver, thread_id: str, user_id: str | None = None
) -> list[dict[str, Any]]:
    """Get checkpoint history for a thread.

    Args:
        checkpointer: Checkpointer instance
        thread_id: Thread ID to get history for
        user_id: Optional user ID for filtering checkpoints

    Returns:
        List of checkpoint metadata dicts

    Example:
        >>> history = get_checkpoint_history(checkpointer, "thread-123")
        >>> for cp in history:
        ...     print(f"Checkpoint: {cp}")
        >>> # With user_id
        >>> history = get_checkpoint_history(checkpointer, "thread-123", user_id="user-1")
    """
    history = []
    configurable = {"thread_id": thread_id}
    if user_id:
        configurable["user_id"] = user_id
    config = RunnableConfig(configurable=configurable)

    for checkpoint_tuple in checkpointer.list(config):
        history.append(
            {
                "checkpoint": checkpoint_tuple.checkpoint,
                "metadata": checkpoint_tuple.metadata,
                "parent_config": checkpoint_tuple.parent_config,
            }
        )
    return history


def delete_checkpoint(checkpointer: BaseCheckpointSaver, thread_id: str) -> None:
    """Delete checkpoint for a thread (if supported by checkpointer).

    Args:
        checkpointer: Checkpointer instance
        thread_id: Thread ID to delete

    Note:
        Memory checkpointer doesn't support deletion (data is cleared on restart)

    Example:
        >>> delete_checkpoint(checkpointer, "old-thread-123")
    """
    # For memory checkpointer, there's no explicit delete method
    # Checkpoints are automatically cleared when the process restarts
    pass
