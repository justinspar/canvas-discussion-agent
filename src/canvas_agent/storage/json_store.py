"""Atomic JSON file persistence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from canvas_agent.models import AgentState
from canvas_agent.storage.protocol import StorageProtocol


class JsonFileStorage:
    """Persists AgentState as JSON with atomic replace."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> AgentState:
        if not self.path.exists():
            return AgentState()
        raw = self.path.read_text(encoding="utf-8")
        if not raw.strip():
            return AgentState()
        return AgentState.model_validate_json(raw)

    def save(self, state: AgentState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = state.model_dump_json(indent=2)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent),
            prefix=f".{self.path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise


# Explicitly satisfy the protocol for type checkers / tests
_: type[StorageProtocol] = JsonFileStorage
