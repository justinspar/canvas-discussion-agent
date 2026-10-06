"""Shared pytest fixtures and fakes."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from canvas_agent.canvas.parse import content_fingerprint, html_to_text, parse_control_status
from canvas_agent.config import Config
from canvas_agent.llm.openai_advisor import StubAdvisor
from canvas_agent.models import (
    AdvisorDecision,
    ControlStatus,
    DiscussionEntry,
    DiscussionSnapshot,
    WriteKind,
)
from canvas_agent.storage.json_store import JsonFileStorage

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def tmp_storage(tmp_path: Path) -> JsonFileStorage:
    return JsonFileStorage(tmp_path / "agent_state.json")


@pytest.fixture
def test_config(tmp_path: Path) -> Config:
    return Config(
        canvas_base_url="https://canvas.mit.edu",
        canvas_token="test-token-secret-value",
        course_id=40577,
        topic_id=448963,
        dry_run=False,
        interval_hours=3,
        max_consecutive_failures=3,
        max_posts_per_hour=3,
        rate_limit_window_seconds=3600,
        llm_api_key=None,
        llm_model="bedrock/claude-sonnet-5",
        llm_base_url="https://parley.api.mit.edu/v1",
        state_path=tmp_path / "agent_state.json",
        lock_path=tmp_path / "agent.lock",
        pending_max_age_hours=6,
    )


class FakeCanvas:
    """In-memory Canvas stand-in for orchestrator tests."""

    def __init__(
        self,
        *,
        topic: dict[str, Any] | None = None,
        view: dict[str, Any] | None = None,
        agent_user_id: int = 100,
        fail_ack_once: bool = False,
    ) -> None:
        self.topic = topic or load_fixture("topic_running.json")
        self.view = view or load_fixture("discussion_view.json")
        self.agent_user_id = agent_user_id
        self.fail_ack_once = fail_ack_once
        self._ack_failed = False
        self.posts: list[dict[str, Any]] = []
        self.next_id = 1000
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def get_self_user_id(self) -> int:
        return self.agent_user_id

    def get_topic(self) -> dict[str, Any]:
        return deepcopy(self.topic)

    def get_control_status(self) -> tuple[ControlStatus, str]:
        message = self.topic.get("message") or ""
        return parse_control_status(message), html_to_text(message)

    def _flatten(self, nodes: list[dict[str, Any]], parent_id: int | None = None) -> list[DiscussionEntry]:
        flat: list[DiscussionEntry] = []
        for node in nodes:
            entry_id = int(node["id"])
            created = node.get("created_at")
            created_at = None
            if created:
                created_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
            flat.append(
                DiscussionEntry(
                    id=entry_id,
                    user_id=node.get("user_id"),
                    parent_id=node.get("parent_id", parent_id),
                    message_text=html_to_text(node.get("message") or ""),
                    created_at=created_at,
                )
            )
            replies = node.get("replies") or []
            if replies:
                flat.extend(self._flatten(replies, parent_id=entry_id))
        return flat

    def get_discussion_view(self) -> DiscussionSnapshot:
        message_html = self.topic.get("message") or ""
        return DiscussionSnapshot(
            topic_id=448963,
            control_status=parse_control_status(message_html),
            topic_message_text=html_to_text(message_html),
            entries=self._flatten(self.view.get("view") or []),
        )

    def _record_post(self, message: str, parent_id: int | None) -> dict[str, Any]:
        entry_id = self.next_id
        self.next_id += 1
        node = {
            "id": entry_id,
            "user_id": self.agent_user_id,
            "parent_id": parent_id,
            "message": message,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "replies": [],
        }
        if parent_id is None:
            self.view.setdefault("view", []).insert(0, node)
        else:
            self._attach_reply(self.view.get("view") or [], parent_id, node)
        self.posts.append({"id": entry_id, "message": message, "parent_id": parent_id})
        return {"id": entry_id, "message": message, "user_id": self.agent_user_id, "parent_id": parent_id}

    def _attach_reply(self, nodes: list[dict[str, Any]], parent_id: int, node: dict[str, Any]) -> bool:
        for item in nodes:
            if int(item["id"]) == parent_id:
                item.setdefault("replies", []).append(node)
                return True
            if self._attach_reply(item.get("replies") or [], parent_id, node):
                return True
        return False

    def create_entry(self, message: str) -> dict[str, Any]:
        created = self._record_post(message, None)
        if self.fail_ack_once and not self._ack_failed:
            self._ack_failed = True
            from canvas_agent.canvas.client import CanvasTransientError

            raise CanvasTransientError("simulated lost acknowledgement")
        return created

    def create_reply(self, entry_id: int, message: str) -> dict[str, Any]:
        created = self._record_post(message, entry_id)
        if self.fail_ack_once and not self._ack_failed:
            self._ack_failed = True
            from canvas_agent.canvas.client import CanvasTransientError

            raise CanvasTransientError("simulated lost acknowledgement")
        return created

    def verify_entry(self, entry_id: int) -> dict[str, Any] | None:
        for entry in self.get_discussion_view().entries:
            if entry.id == entry_id:
                return {
                    "id": entry.id,
                    "user_id": entry.user_id,
                    "parent_id": entry.parent_id,
                    "message": entry.message_text,
                }
        return None

    def get_entries_by_ids(self, entry_ids: list[int]) -> list[dict[str, Any]]:
        found = []
        for entry in self.get_discussion_view().entries:
            if entry.id in entry_ids:
                found.append(
                    {
                        "id": entry.id,
                        "user_id": entry.user_id,
                        "parent_id": entry.parent_id,
                        "message": entry.message_text,
                    }
                )
        return found


def make_post_decision(
    message: str = "A useful new point about evaluation rigor.",
    *,
    kind: WriteKind = WriteKind.ENTRY,
    parent_id: int | None = None,
) -> AdvisorDecision:
    return AdvisorDecision(
        action="post",
        kind=kind,
        parent_id=parent_id,
        message=message,
        rationale="test",
    )


def fingerprint(message: str, parent_id: int | None = None) -> str:
    return content_fingerprint(message, parent_id)
