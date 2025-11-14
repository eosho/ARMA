"""Factory for creating and managing checkpointers."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver


class CheckpointerFactory:
    """Factory for creating checkpointer instances."""

    @staticmethod
    def create_memory() -> MemorySaver:
        """Create an in-memory checkpointer (no persistence).

        Returns:
            MemorySaver instance

        Example:
            >>> checkpointer = CheckpointerFactory.create_memory()
        """
        return MemorySaver()

    @classmethod
    def create(cls, checkpointer_type: str = "memory") -> BaseCheckpointSaver:
        """Create a checkpointer of the specified type.

        Args:
            checkpointer_type: Type of checkpointer to create ("memory")

        Returns:
            Checkpointer instance

        Raises:
            ValueError: If checkpointer_type is not supported

        Example:
            >>> checkpointer = CheckpointerFactory.create("memory")
        """
        if checkpointer_type == "memory":
            return cls.create_memory()
        else:
            raise ValueError(f"Unsupported checkpointer type: {checkpointer_type}")


# Convenience function for backward compatibility
def create_memory_checkpointer() -> MemorySaver:
    """Create an in-memory checkpointer (no persistence).

    Returns:
        MemorySaver instance

    Example:
        >>> checkpointer = create_memory_checkpointer()
    """
    return CheckpointerFactory.create_memory()
