"""Writes must not be blindly retried after ambiguous transport failures."""

from __future__ import annotations

import httpx
import pytest

from canvas_agent.canvas.client import CanvasAmbiguousWriteError, CanvasClient


def test_write_timeout_is_single_attempt() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.method == "POST":
            raise httpx.ReadTimeout("simulated lost ack", request=request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = CanvasClient(
        "https://canvas.mit.edu",
        "test-token",
        40577,
        448963,
        transport=transport,
        max_retries=5,
        sleep_fn=lambda _s: None,
    )
    try:
        with pytest.raises(CanvasAmbiguousWriteError):
            client.create_entry("hello")
    finally:
        client.close()
    assert calls["n"] == 1
