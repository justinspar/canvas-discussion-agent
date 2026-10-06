"""Canvas client retry / backoff behavior."""

from __future__ import annotations

import httpx
import pytest

from canvas_agent.canvas.client import CanvasClient, CanvasTransientError
from canvas_agent.logging_utils import redact


def test_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"errors": ["unavailable"]})
        return httpx.Response(200, json={"id": 42, "name": "Agent"})

    transport = httpx.MockTransport(handler)
    sleeps: list[float] = []
    client = CanvasClient(
        "https://canvas.mit.edu",
        "super-secret-token",
        40577,
        448963,
        transport=transport,
        max_retries=5,
        sleep_fn=sleeps.append,
        rng=__import__("random").Random(0),
    )
    try:
        user_id = client.get_self_user_id()
    finally:
        client.close()
    assert user_id == 42
    assert calls["n"] == 3
    assert len(sleeps) == 2


def test_exhausted_retries_raise() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"errors": ["unavailable"]})

    transport = httpx.MockTransport(handler)
    client = CanvasClient(
        "https://canvas.mit.edu",
        "super-secret-token",
        40577,
        448963,
        transport=transport,
        max_retries=2,
        sleep_fn=lambda _s: None,
        rng=__import__("random").Random(0),
    )
    try:
        with pytest.raises(CanvasTransientError):
            client.get_self_user_id()
    finally:
        client.close()


def test_token_not_in_error_or_redaction() -> None:
    token = "super-secret-token"
    text = f"Authorization: Bearer {token} failed"
    assert token not in redact(text, [token])
    assert "***REDACTED***" in redact(text, [token])
