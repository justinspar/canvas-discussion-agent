"""Canvas HTML formatting — peer-like structure, safe allowlist."""

from __future__ import annotations

from canvas_agent.canvas.parse import (
    html_to_text,
    plain_text_to_canvas_html,
    sanitize_canvas_html,
)
from canvas_agent.models import AdvisorDecision, WriteKind
from canvas_agent.safety.output_guard import validate_decision


def test_plain_text_to_canvas_html_preserves_fenced_code() -> None:
    msg = (
        "Please test this function:\n\n"
        "```python\n"
        "def dedupe(items):\n"
        "    if not isinstance(items, list):\n"
        "        raise TypeError('bad')\n"
        "    return list(dict.fromkeys(items))\n"
        "```\n\n"
        "Deadline: 24h"
    )
    html = plain_text_to_canvas_html(msg)
    assert "<pre><code>" in html
    assert "<p>" in html
    assert "def dedupe(items):" in html
    assert "    if not isinstance" in html
    roundtrip = html_to_text(html)
    assert "def dedupe(items):" in roundtrip
    assert "    if not isinstance" in roundtrip


def test_structured_lists_and_bold() -> None:
    msg = (
        "SERVICE OFFER: Demo\n\n"
        "What it does:\n\n"
        "- first item\n"
        "- second **important** item\n\n"
        "Turnaround: every few hours"
    )
    html = plain_text_to_canvas_html(msg)
    assert "<ul>" in html
    assert "<li>" in html
    assert "<strong>important</strong>" in html
    assert "<p>" in html


def test_sanitize_keeps_allowlist_strips_script() -> None:
    raw = (
        "<p>Hello <strong>world</strong></p>"
        "<script>alert(1)</script>"
        "<p onclick='x'>safe</p>"
    )
    clean = sanitize_canvas_html(raw)
    assert "<script>" not in clean
    assert "alert" not in clean
    assert "<strong>world</strong>" in clean
    assert "onclick" not in clean
    assert "<p>safe</p>" in clean


def test_output_guard_allows_safe_html() -> None:
    decision = validate_decision(
        AdvisorDecision(
            action="post",
            kind=WriteKind.ENTRY,
            message="<p>Useful point about <strong>sampling</strong>.</p>"
            "<script>alert(1)</script>",
        )
    )
    assert decision.message is not None
    assert "<script>" not in decision.message
    assert "<p>" in decision.message
    assert "<strong>sampling</strong>" in decision.message


def test_existing_html_passthrough_sanitized() -> None:
    msg = "<p><strong>SERVICE OFFER:</strong> Checklist</p><ul><li>One</li></ul>"
    html = plain_text_to_canvas_html(msg)
    assert html.startswith("<p>")
    assert "<ul>" in html
