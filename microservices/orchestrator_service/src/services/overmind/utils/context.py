"""
Collaboration Context Implementation.
Implements the CollaborationContext protocol.
"""


class InMemoryCollaborationContext:
    """
    In-memory implementation of CollaborationContext.
    """

    def __init__(self, initial_data: dict[str, object] | None = None) -> None:
        self.shared_memory: dict[str, object] = initial_data or {}

    def update(self, key: str, value: object) -> None:
        """Update a value in shared memory."""
        self.shared_memory[key] = value

    def get(self, key: str) -> object | None:
        """Get a value from shared memory."""
        return self.shared_memory.get(key)
