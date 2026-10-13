"""Canvas HTML formatting preserves code for pytest hires."""

from __future__ import annotations

from canvas_agent.canvas.parse import html_to_text, plain_text_to_canvas_html


def test_plain_text_to_canvas_html_preserves_fenced_code() -> None:
    msg = (
        "Please test this function:\n"
        "```python\n"
        "def dedupe(items):\n"
        "    if not isinstance(items, list):\n"
        "        raise TypeError('bad')\n"
        "    return list(dict.fromkeys(items))\n"
        "```\n"
        "Deadline: 24h"
    )
    html = plain_text_to_canvas_html(msg)
    assert "<pre><code>" in html
    assert "def dedupe(items):" in html
    assert "    if not isinstance" in html
    assert "<br>" in html
    roundtrip = html_to_text(html)
    assert "def dedupe(items):" in roundtrip
    assert "    if not isinstance" in roundtrip


def test_agentic_rejects_pytest_hire_without_fenced_source() -> None:
    import json

    from canvas_agent.hw4.agentic import decide_next
    from canvas_agent.hw4.phases import Hw4Idle
    from canvas_agent.models import (
        AgentState,
        ControlStatus,
        DiscussionEntry,
        DiscussionSnapshot,
        Hw4State,
        OfferStatus,
    )

    class _FakeChoice:
        def __init__(self, content: str) -> None:
            self.message = type("M", (), {"content": content})()

    class _FakeClient:
        def __init__(self, content: str) -> None:
            self._content = content

            class _Comp:
                def __init__(self, outer: "_FakeClient") -> None:
                    self._outer = outer

                def create(self, **kwargs):  # noqa: ANN003
                    return type(
                        "R", (), {"choices": [_FakeChoice(self._outer._content)]}
                    )()

            self.chat = type("C", (), {"completions": _Comp(self)})()

    payload = {
        "action": "post",
        "intent": "delegate",
        "kind": "reply",
        "parent_id": 55,
        "message": (
            "Please write pytest for dedupe_preserve_order. "
            "def dedupe_preserve_order(items): return items\n"
            "Deadline 24h."
        ),
        "rationale": "hire pytest",
        "meta": {"provider_entry_id": 55, "deadline_hours": 24},
    }
    state = AgentState(
        agent_user_id=100,
        hw4=Hw4State(
            offer_status=OfferStatus.VERIFIED,
            offer_entry_id=10,
            offer_verified=True,
            offer_clarification_id=10,
        ),
    )
    snap = DiscussionSnapshot(
        topic_id=449948,
        control_status=ControlStatus.RUNNING,
        entries=[
            DiscussionEntry(
                id=10,
                user_id=100,
                parent_id=None,
                message_text="SERVICE OFFER: x\n**What I need from you**",
            ),
            DiscussionEntry(
                id=55,
                user_id=200,
                parent_id=None,
                message_text=(
                    "SERVICE OFFER: unit tests for your Python function (pytest)\n"
                    "Input: function source code in a code block."
                ),
            ),
        ],
    )
    action = decide_next(
        state,
        snap,
        llm_client=_FakeClient(json.dumps(payload)),
        llm_model="bedrock/claude-sonnet-5",
    )
    assert isinstance(action, Hw4Idle)
    assert "missing_fenced_source" in action.rationale
