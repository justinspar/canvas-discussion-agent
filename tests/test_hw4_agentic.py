"""Agentic Parley decide+draft for HW4."""

from __future__ import annotations

import json

from canvas_agent.hw4.agentic import decide_next
from canvas_agent.hw4.phases import Hw4Idle, Hw4PlannedWrite
from canvas_agent.models import (
    AgentState,
    ControlStatus,
    DiscussionEntry,
    DiscussionSnapshot,
    Hw4State,
    OfferStatus,
    WriteKind,
)


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = type("M", (), {"content": content})()


class _FakeClient:
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls = 0

        class _Comp:
            def __init__(self, outer: "_FakeClient") -> None:
                self._outer = outer

            def create(self, **kwargs):  # noqa: ANN003
                self._outer.calls += 1
                return type("R", (), {"choices": [_FakeChoice(self._outer._content)]})()

        self.chat = type("C", (), {"completions": _Comp(self)})()


def _snap(*entries: DiscussionEntry) -> DiscussionSnapshot:
    return DiscussionSnapshot(
        topic_id=449948, control_status=ControlStatus.RUNNING, entries=list(entries)
    )


def test_agentic_posts_offer_when_needed() -> None:
    payload = {
        "action": "post",
        "intent": "offer",
        "kind": "entry",
        "parent_id": None,
        "message": "SERVICE OFFER: Agent Red-Team Service\nI review agents.",
        "rationale": "need to advertise service",
        "meta": {},
    }
    client = _FakeClient(json.dumps(payload))
    state = AgentState(agent_user_id=100)
    action = decide_next(
        state,
        _snap(),
        llm_client=client,
        llm_model="bedrock/claude-sonnet-5",
    )
    assert isinstance(action, Hw4PlannedWrite)
    assert action.kind is WriteKind.ENTRY
    assert action.meta.get("type") == "offer"
    assert "SERVICE OFFER" in action.message
    assert client.calls == 1


def test_agentic_abstain() -> None:
    client = _FakeClient(
        json.dumps(
            {
                "action": "abstain",
                "intent": "other",
                "kind": None,
                "parent_id": None,
                "message": None,
                "rationale": "waiting_for_provider",
                "meta": {},
            }
        )
    )
    state = AgentState(
        agent_user_id=100,
        hw4=Hw4State(
            offer_status=OfferStatus.VERIFIED,
            offer_entry_id=10,
            offer_verified=True,
        ),
    )
    action = decide_next(
        state,
        _snap(
            DiscussionEntry(
                id=10,
                user_id=100,
                parent_id=None,
                message_text="SERVICE OFFER: Agent Red-Team Service\n**What I need from you**",
            )
        ),
        llm_client=client,
        llm_model="bedrock/claude-sonnet-5",
    )
    assert isinstance(action, Hw4Idle)
    assert "waiting" in action.rationale


def test_agentic_delegate_sets_provider_meta() -> None:
    payload = {
        "action": "post",
        "intent": "delegate",
        "kind": "reply",
        "parent_id": 55,
        "message": (
            "<p>Service request — you offered pytest for agents.</p>"
            "<p>Please design edge-case tests for:</p>"
            "<pre><code>def add(a, b):\n    return a + b\n</code></pre>"
            "<p>Deadline: soon</p>"
        ),
        "rationale": "hire testing peer",
        "meta": {
            "provider_entry_id": 55,
            "task_description": "edge-case tests",
            "acceptance_criteria": "3 cases",
            "deadline_hours": 36,
        },
    }
    client = _FakeClient(json.dumps(payload))
    state = AgentState(
        agent_user_id=100,
        hw4=Hw4State(
            offer_status=OfferStatus.VERIFIED,
            offer_entry_id=10,
            offer_verified=True,
            offer_clarification_id=10,
        ),
    )
    action = decide_next(
        state,
        _snap(
            DiscussionEntry(
                id=10,
                user_id=100,
                parent_id=None,
                message_text="SERVICE OFFER: Agent Red-Team Service\n**What I need from you**",
            ),
            DiscussionEntry(
                id=55,
                user_id=200,
                parent_id=None,
                message_text="SERVICE OFFER: pytest for autonomous Canvas agents",
            ),
        ),
        llm_client=client,
        llm_model="bedrock/claude-sonnet-5",
    )
    assert isinstance(action, Hw4PlannedWrite)
    assert action.parent_id == 55
    assert action.meta.get("type") == "delegate"
    assert action.meta.get("deadline") is not None
