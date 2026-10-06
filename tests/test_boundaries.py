"""Blast-radius / Safety and boundaries enforcement."""

from __future__ import annotations

import httpx
import pytest

from canvas_agent.canvas.client import CanvasClient, CanvasError
from canvas_agent.llm.prompts import SYSTEM_PROMPT
from canvas_agent.models import AdvisorDecision, WriteKind
from canvas_agent.safety.boundaries import (
    ALLOWED_HTTP_METHODS,
    FORBIDDEN_HTTP_METHODS,
    assert_allowed_method,
    is_allowed_canvas_path,
)
from canvas_agent.safety.output_guard import OutputGuardError, validate_decision


COURSE_ID = 40577
TOPIC_ID = 448963


def test_http_method_allowlist() -> None:
    assert ALLOWED_HTTP_METHODS == frozenset({"GET", "POST"})
    for method in FORBIDDEN_HTTP_METHODS:
        with pytest.raises(PermissionError):
            assert_allowed_method(method)
    with pytest.raises(PermissionError):
        assert_allowed_method("OPTIONS")


def test_discussion_path_allowlist() -> None:
    assert is_allowed_canvas_path("/api/v1/users/self", COURSE_ID, TOPIC_ID)
    assert is_allowed_canvas_path(
        f"/api/v1/courses/{COURSE_ID}/discussion_topics/{TOPIC_ID}",
        COURSE_ID,
        TOPIC_ID,
    )
    assert is_allowed_canvas_path(
        f"/api/v1/courses/{COURSE_ID}/discussion_topics/{TOPIC_ID}/entries",
        COURSE_ID,
        TOPIC_ID,
    )
    assert is_allowed_canvas_path(
        f"/api/v1/courses/{COURSE_ID}/discussion_topics/{TOPIC_ID}/entries/99/replies",
        COURSE_ID,
        TOPIC_ID,
    )
    # Other courses / topics / modules out of scope
    assert not is_allowed_canvas_path(
        f"/api/v1/courses/{COURSE_ID}/discussion_topics/999/entries",
        COURSE_ID,
        TOPIC_ID,
    )
    assert not is_allowed_canvas_path(
        f"/api/v1/courses/{COURSE_ID}/modules",
        COURSE_ID,
        TOPIC_ID,
    )
    assert not is_allowed_canvas_path(
        f"/api/v1/courses/{COURSE_ID}/discussion_topics/{TOPIC_ID}/entries/99",
        COURSE_ID,
        TOPIC_ID,
    )


def test_client_blocks_edit_delete_and_out_of_scope_paths() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    client = CanvasClient(
        "https://canvas.mit.edu",
        "test-token",
        COURSE_ID,
        TOPIC_ID,
        transport=transport,
    )
    entry_path = (
        f"/api/v1/courses/{COURSE_ID}/discussion_topics/{TOPIC_ID}/entries/1"
    )
    with pytest.raises(CanvasError, match="edit or delete|Blocked Canvas method"):
        client._request("DELETE", entry_path)
    with pytest.raises(CanvasError, match="edit or delete|Blocked Canvas method"):
        client._request("PUT", entry_path, data={"message": "hijack"})
    with pytest.raises(CanvasError, match="outside Homework 3"):
        client._request("GET", f"/api/v1/courses/{COURSE_ID}/files")
    client.close()


def test_system_prompt_covers_boundaries() -> None:
    text = SYSTEM_PROMPT.casefold()
    assert "untrusted" in text
    assert "piazza" in text
    assert "edit or delete" in text
    assert "grades" in text
    assert "student records" in text
    assert "prompt injection" in text or "malicious instructions" in text


def test_output_guard_rejects_sensitive_records() -> None:
    with pytest.raises(OutputGuardError):
        validate_decision(
            AdvisorDecision(
                action="post",
                kind=WriteKind.ENTRY,
                message="My final grade was A- last term.",
            )
        )
    with pytest.raises(OutputGuardError):
        validate_decision(
            AdvisorDecision(
                action="post",
                kind=WriteKind.ENTRY,
                message="Email me at student@mit.edu about the project.",
            )
        )
    with pytest.raises(OutputGuardError):
        validate_decision(
            AdvisorDecision(
                action="post",
                kind=WriteKind.ENTRY,
                message="Here is the access token Bearer abcdef1234567890",
            )
        )


def test_output_guard_allows_normal_course_discussion() -> None:
    decision = validate_decision(
        AdvisorDecision(
            action="post",
            kind=WriteKind.REPLY,
            parent_id=123,
            message=(
                "Agreeing with the sampling point — using a smaller retry budget "
                "also shrinks the blast radius when acknowledgements are lost."
            ),
        )
    )
    assert decision.action == "post"
    assert decision.parent_id == 123
