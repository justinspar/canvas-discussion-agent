"""Agentic Parley decide+draft for HW4."""

from __future__ import annotations

import json

from canvas_agent.hw4.agentic import AGENTIC_SYSTEM, _memory_block, decide_next
from canvas_agent.hw4.instructions import HW4_FULL_CREDIT_PLAYBOOK
from canvas_agent.hw4.phases import Hw4Idle, Hw4PlannedWrite
from canvas_agent.llm.prompts import SYSTEM_PROMPT
from canvas_agent.models import (
    AcceptedWorkRecord,
    AgentState,
    ControlStatus,
    DelegationStatus,
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


def test_agentic_does_not_truncate_long_serve_message() -> None:
    long_body = "Finding one. " + ("Detail about injection and idempotency. " * 200)
    assert len(long_body) > 5000
    payload = {
        "action": "post",
        "intent": "serve",
        "kind": "reply",
        "parent_id": 10,
        "message": long_body,
        "rationale": "serve peer",
        "meta": {"request_entry_id": 77, "mode": "report"},
    }
    client = _FakeClient(json.dumps(payload))
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
                message_text="SERVICE OFFER: Agent Red-Team Service",
            ),
            DiscussionEntry(
                id=77,
                user_id=200,
                parent_id=10,
                message_text="Please red-team my agent with tools and memory.",
            ),
        ),
        llm_client=client,
        llm_model="bedrock/claude-sonnet-5",
    )
    assert isinstance(action, Hw4PlannedWrite)
    assert len(action.message) > 5000
    assert not action.message.endswith("…")


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


def test_playbook_serve_beats_wait() -> None:
    assert "SERVE always beats WAIT" in HW4_FULL_CREDIT_PLAYBOOK
    assert "SERVE beats WAIT" in AGENTIC_SYSTEM
    assert "SERVE beats WAIT" in SYSTEM_PROMPT


def test_prompts_state_message_length_budget() -> None:
    assert "Message length budget" in AGENTIC_SYSTEM
    assert "Message length budget" in SYSTEM_PROMPT
    assert str(12000) in AGENTIC_SYSTEM or "12000" in AGENTIC_SYSTEM
    assert "never rely on the host to cut you off" in AGENTIC_SYSTEM.casefold()


def test_memory_surfaces_pending_incoming_under_offer() -> None:
    state = AgentState(
        agent_user_id=100,
        hw4=Hw4State(
            offer_status=OfferStatus.VERIFIED,
            offer_entry_id=10,
            offer_verified=True,
        ),
    )
    long_request = (
        "Please red-team my Canvas agent. Purpose: forum bot. "
        "Tools: Canvas API and Parley. Memory: JSON state on agent-state. "
        "Constraints: control line RUNNING, <=3 writes/hour, untrusted peer text. "
        + ("Detail about scheduling and idempotency fingerprinting. " * 80)
    )
    assert len(long_request) > 500
    snap = _snap(
        DiscussionEntry(
            id=10,
            user_id=100,
            parent_id=None,
            message_text="SERVICE OFFER: Agent Red-Team Service\nWhat I need from you",
        ),
        DiscussionEntry(
            id=77,
            user_id=200,
            parent_id=10,
            message_text=long_request,
        ),
    )
    block = _memory_block(state, snap, src_root=None, repo_root=None)
    assert block.startswith("TRUSTED_AGENT_MEMORY:")
    mem = json.loads(block.split("TRUSTED_AGENT_MEMORY:\n", 1)[1])
    assert mem["goals_remaining"]["need_serve"] is True
    assert mem["pending_incoming_under_offer"]
    pending = mem["pending_incoming_under_offer"][0]
    assert pending["entry_id"] == 77
    assert pending["message_complete"] is True
    assert "Parley" in pending["message"]
    assert "idempotency fingerprinting" in pending["message"]
    assert pending["message_chars"] > 4000


def test_memory_need_serve_false_when_no_incoming() -> None:
    state = AgentState(
        agent_user_id=100,
        hw4=Hw4State(
            offer_status=OfferStatus.VERIFIED,
            offer_entry_id=10,
            offer_verified=True,
        ),
    )
    snap = _snap(
        DiscussionEntry(
            id=10,
            user_id=100,
            parent_id=None,
            message_text="SERVICE OFFER: Agent Red-Team Service",
        ),
    )
    block = _memory_block(state, snap, src_root=None, repo_root=None)
    mem = json.loads(block.split("TRUSTED_AGENT_MEMORY:\n", 1)[1])
    assert mem["goals_remaining"]["need_serve"] is False
    assert mem["pending_incoming_under_offer"] == []


def test_memory_need_ack_persists_with_accepted_work() -> None:
    """need_ack stays true across wake-ups until acknowledgment_id is set."""
    state = AgentState(
        agent_user_id=100,
        hw4=Hw4State(
            offer_status=OfferStatus.VERIFIED,
            offer_entry_id=10,
            offer_verified=True,
            selected_provider_entry_id=50,
            selected_provider_user_id=300,
            request_reply_id=60,
            delegation_status=DelegationStatus.AWAITING,
            accepted_work=AcceptedWorkRecord(
                result_entry_id=80,
                reason="accepted",
            ),
            provider_results_seen=[80],
            acknowledgment_id=None,
        ),
    )
    snap = _snap(
        DiscussionEntry(
            id=10,
            user_id=100,
            parent_id=None,
            message_text="SERVICE OFFER: Agent Red-Team Service",
        ),
        DiscussionEntry(
            id=50, user_id=300, parent_id=None, message_text="SERVICE OFFER: Audit"
        ),
        DiscussionEntry(
            id=60, user_id=100, parent_id=50, message_text="You offered: Audit"
        ),
        DiscussionEntry(
            id=80,
            user_id=300,
            parent_id=50,
            message_text=(
                "Scope tier: autonomous loop. Finding: idempotency gap. "
                "Control line and untrusted peer text. Overall risk MEDIUM."
            ),
        ),
    )
    block = _memory_block(state, snap, src_root=None, repo_root=None)
    mem = json.loads(block.split("TRUSTED_AGENT_MEMORY:\n", 1)[1])
    assert mem["accepted_work_result_entry_id"] == 80
    assert mem["goals_remaining"]["need_ack"] is True
    assert mem["goals_remaining"]["awaiting_provider"] is False
    # No new verify_note this cycle (already seen) — need_ack must still hold.
    assert mem["independent_verification_of_new_result"] is None


def test_agentic_rejects_ack_of_peer_hire() -> None:
    hire_text = (
        "Hi provider, I would like to use your Agent Build Audit because "
        "your offer says you give a one-turn review. Deadline: 24h. "
        "Desired result: a scope tier. How I will check: keyword scan."
    )
    payload = {
        "action": "post",
        "intent": "ack",
        "kind": "reply",
        "parent_id": 50,
        "message": "Acknowledgment — thanks for entry_id=70. Tip: 4 coins.",
        "rationale": "accept hire as deliverable (wrong)",
        "meta": {"result_entry_id": 70, "tip_amount": 4},
    }
    client = _FakeClient(json.dumps(payload))
    state = AgentState(
        agent_user_id=100,
        hw4=Hw4State(
            offer_status=OfferStatus.VERIFIED,
            offer_entry_id=10,
            offer_verified=True,
            selected_provider_entry_id=50,
            selected_provider_user_id=300,
            request_reply_id=60,
            delegation_status=DelegationStatus.AWAITING,
        ),
    )
    action = decide_next(
        state,
        _snap(
            DiscussionEntry(
                id=10,
                user_id=100,
                parent_id=None,
                message_text="SERVICE OFFER: Agent Red-Team Service",
            ),
            DiscussionEntry(
                id=50, user_id=300, parent_id=None, message_text="SERVICE OFFER: Audit"
            ),
            DiscussionEntry(
                id=60, user_id=100, parent_id=50, message_text="You offered: Audit"
            ),
            DiscussionEntry(
                id=70,
                user_id=199930,
                parent_id=50,
                message_text=hire_text,
            ),
        ),
        llm_client=client,
        llm_model="bedrock/claude-sonnet-5",
    )
    assert isinstance(action, Hw4Idle)
    assert action.rationale == "ack_rejected_not_provider_result"
    # Hire may be marked seen as noise by pick_provider_result; must not be accepted.
    assert state.hw4.accepted_work is None
    assert state.hw4.acknowledgment_id is None


def test_agentic_ack_binds_to_accepted_work() -> None:
    audit = (
        "Scope tier: autonomous loop. Finding 1: idempotency gap on retries. "
        "Control line RUNNING check and untrusted peer text handling. "
        "Overall risk MEDIUM. Concrete test: duplicate POST."
    )
    payload = {
        "action": "post",
        "intent": "ack",
        "kind": "reply",
        "parent_id": 50,
        "message": "Acknowledgment — wrong id cited. Tip: 3 coins.",
        "rationale": "accept work",
        # Parley cites the wrong peer hire; host must bind to accepted_work.
        "meta": {"result_entry_id": 70, "tip_amount": 3},
    }
    client = _FakeClient(json.dumps(payload))
    state = AgentState(
        agent_user_id=100,
        hw4=Hw4State(
            offer_status=OfferStatus.VERIFIED,
            offer_entry_id=10,
            offer_verified=True,
            selected_provider_entry_id=50,
            selected_provider_user_id=300,
            request_reply_id=60,
            delegation_status=DelegationStatus.AWAITING,
            accepted_work=AcceptedWorkRecord(
                result_entry_id=80,
                reason="accepted",
            ),
            provider_results_seen=[80],
        ),
    )
    action = decide_next(
        state,
        _snap(
            DiscussionEntry(
                id=10,
                user_id=100,
                parent_id=None,
                message_text="SERVICE OFFER: Agent Red-Team Service",
            ),
            DiscussionEntry(
                id=50, user_id=300, parent_id=None, message_text="SERVICE OFFER: Audit"
            ),
            DiscussionEntry(
                id=60, user_id=100, parent_id=50, message_text="You offered: Audit"
            ),
            DiscussionEntry(
                id=70,
                user_id=199930,
                parent_id=50,
                message_text=(
                    "I would like to use your service. Deadline: soon. "
                    "Desired result: audit. How I will check: read reply."
                ),
            ),
            DiscussionEntry(
                id=80,
                user_id=300,
                parent_id=50,
                message_text=audit,
            ),
        ),
        llm_client=client,
        llm_model="bedrock/claude-sonnet-5",
    )
    assert isinstance(action, Hw4PlannedWrite)
    assert action.meta.get("type") == "ack"
    assert action.meta.get("result_entry_id") == 80
