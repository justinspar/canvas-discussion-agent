"""Storage package."""

from canvas_agent.storage.json_store import JsonFileStorage
from canvas_agent.storage.protocol import StorageProtocol

__all__ = ["JsonFileStorage", "StorageProtocol"]
