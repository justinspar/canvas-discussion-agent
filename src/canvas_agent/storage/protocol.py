"""Storage interface for persistent agent memory."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from canvas_agent.models import AgentState


@runtime_checkable
class StorageProtocol(Protocol):
    def load(self) -> AgentState:
        """Load agent state; return empty state if missing."""

    def save(self, state: AgentState) -> None:
        """Persist agent state atomically."""
