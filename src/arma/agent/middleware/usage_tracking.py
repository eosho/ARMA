"""Usage tracking middleware for monitoring token consumption and costs.

This middleware tracks LLM usage metrics"""

from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from arma.core.logging import get_logger

logger = get_logger(__name__)


class UsageTrackingMiddleware(AgentMiddleware):
    """Track LLM usage metrics and costs."""

    def __init__(self) -> None:
        """Initialize usage tracking middleware."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0

    @property
    def name(self) -> str:
        """Return the middleware name identifier."""
        return "usage_tracking"

    def after_model(
        self, state: AgentState, runtime: Runtime
    ) -> dict[str, Any] | None:  # noqa: ARG002
        """Track usage after model call.

        Args:
            state: Current agent state
            runtime: Runtime context

        Returns:
            None (no state modifications)
        """
        # Get the last message (should be AIMessage from model)
        if not state.get("messages"):
            return None

        last_message = state["messages"][-1]
        if not isinstance(last_message, AIMessage):
            return None

        # Extract usage metadata if available
        if hasattr(last_message, "usage_metadata") and last_message.usage_metadata:
            usage = last_message.usage_metadata
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

            # Update totals
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_calls += 1

            # Log usage
            logger.info(
                "Token usage: input=%s tokens, output=%s tokens, total=%s tokens",
                f"{input_tokens:,}",
                f"{output_tokens:,}",
                f"{total_tokens:,}",
            )

            logger.info(
                "Session totals: input=%s tokens, output=%s tokens, total=%s tokens, calls=%s",
                f"{self.total_input_tokens:,}",
                f"{self.total_output_tokens:,}",
                f"{(self.total_input_tokens + self.total_output_tokens):,}",
                self.total_calls,
            )

        return None

    def get_stats(self) -> dict[str, int]:
        """Get current usage statistics.

        Returns:
            Dictionary with usage stats
        """
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_calls": self.total_calls,
        }

    def reset_stats(self) -> None:
        """Reset usage statistics."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0
