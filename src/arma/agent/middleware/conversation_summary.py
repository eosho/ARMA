"""Conversation summary middleware for managing conversation memory.

This middleware manages the conversation window by trimming old messages
when the context grows too large.
"""

from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from arma.core.logging import get_logger

logger = get_logger(__name__)


class ConversationSummaryMiddleware(AgentMiddleware):
    """Trim conversation history when it grows too large."""

    @property
    def name(self) -> str:
        """Return the middleware name identifier."""
        return "conversation_summary"

    def __init__(self, max_messages: int = 20):
        """Initialize middleware with max message count.

        Args:
            max_messages: Maximum number of messages to keep (default: 20)
        """
        super().__init__()
        self.max_messages = max_messages

    def before_model(
        self, state: AgentState, runtime: Runtime
    ) -> dict[str, Any] | None:  # noqa: ARG002
        """Trim conversation history when it grows too large.

        This middleware:
        1. Monitors message count
        2. Trims old messages while keeping recent context
        3. Preserves important state in messages

        Args:
            state: Current agent state
            runtime: Runtime context

        Returns:
            State updates with trimmed messages, or None
        """
        messages = state.get("messages", [])

        # Ensure messages is a list
        if not isinstance(messages, list):
            return None

        # Only trim if we exceed the limit
        if len(messages) <= self.max_messages:
            return None

        logger.info(
            f"[ConversationSummary] Trimming from {len(messages)} to {self.max_messages} messages"
        )

        # Keep system messages and recent conversation
        system_messages = [msg for msg in messages if isinstance(msg, SystemMessage)]
        other_messages = [msg for msg in messages if not isinstance(msg, SystemMessage)]

        # Keep the most recent messages
        trimmed_messages = system_messages + other_messages[-self.max_messages :]

        # Add a summary message about what was removed
        if len(other_messages) > self.max_messages:
            removed_count = len(other_messages) - self.max_messages
            summary_msg = SystemMessage(
                content=f"[Previous conversation with {removed_count} messages was summarized to keep context manageable]"
            )
            trimmed_messages.insert(len(system_messages), summary_msg)

        return {"messages": trimmed_messages}
