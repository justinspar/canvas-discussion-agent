"""Malformed Canvas payloads fail safely without writes."""

from __future__ import annotations

import httpx
import pytest

from canvas_agent.canvas.client import CanvasClient, CanvasError


def test_malformed_users_self_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"name": "no-id"})

    client = CanvasClient(
        "https://canvas.mit.edu",
        "test-token",
        40577,
        448963,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _s: None,
    )
    try:
        with pytest.raises(CanvasError, match="Malformed"):
            client.get_self_user_id()
    finally:
        client.close()


def test_malformed_view_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/view"):
            return httpx.Response(200, content=b"not-json", headers={"content-type": "application/json"})
        if "discussion_topics/448963" in request.url.path and not request.url.path.endswith(
            "/view"
        ):
            return httpx.Response(
                200,
                json={"id": 448963, "message": "<p>COURSE-TEAM CONTROL: RUNNING</p>"},
            )
        return httpx.Response(200, json={"id": 1})

    client = CanvasClient(
        "https://canvas.mit.edu",
        "test-token",
        40577,
        448963,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _s: None,
    )
    try:
        with pytest.raises(CanvasError, match="Malformed"):
            client.get_discussion_view()
    finally:
        client.close()
