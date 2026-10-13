"""Provider result selection must ignore other peers hiring the same offer."""

from __future__ import annotations

from canvas_agent.hw4.sanitize_peer import (
    looks_like_peer_hire_request,
    pick_provider_result,
)
from canvas_agent.models import (
    ControlStatus,
    DiscussionEntry,
    DiscussionSnapshot,
    Hw4State,
)


def test_looks_like_peer_hire_request() -> None:
    hire = (
        "Hi Natsharee, I would like to use your Agent Build Audit because "
        "your offer says you give a one-turn review. Deadline: 24h."
    )
    report = (
        "Scope tier: autonomous loop. Finding 1: control line race. "
        "Overall risk: MEDIUM. Concrete test: pause forum and confirm no POST."
    )
    assert looks_like_peer_hire_request(hire) is True
    assert looks_like_peer_hire_request(report) is False


def test_pick_provider_result_skips_other_peer_hire() -> None:
    hw4 = Hw4State(
        selected_provider_entry_id=50,
        selected_provider_user_id=300,
        request_reply_id=60,
    )
    snap = DiscussionSnapshot(
        topic_id=449948,
        control_status=ControlStatus.RUNNING,
        entries=[
            DiscussionEntry(
                id=50, user_id=300, parent_id=None, message_text="SERVICE OFFER: Audit"
            ),
            DiscussionEntry(
                id=60,
                user_id=100,
                parent_id=50,
                message_text="You offered: Audit\nTask: please review my agent",
            ),
            DiscussionEntry(
                id=70,
                user_id=199930,
                parent_id=50,
                message_text=(
                    "Hi provider, I would like to use your Agent Build Audit "
                    "service. Deadline: soon."
                ),
            ),
            DiscussionEntry(
                id=80,
                user_id=300,
                parent_id=50,
                message_text=(
                    "Scope tier: autonomous loop. Finding: idempotency gap. "
                    "Overall risk MEDIUM. Concrete test: duplicate POST."
                ),
            ),
        ],
    )
    result, noise = pick_provider_result(snap, hw4, agent_user_id=100)
    assert noise == [70]
    assert result is not None
    assert result.id == 80


def test_pick_provider_result_waits_when_only_noise() -> None:
    hw4 = Hw4State(
        selected_provider_entry_id=50,
        selected_provider_user_id=300,
        request_reply_id=60,
    )
    snap = DiscussionSnapshot(
        topic_id=449948,
        control_status=ControlStatus.RUNNING,
        entries=[
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
                message_text="I would like to use your service offer please.",
            ),
        ],
    )
    result, noise = pick_provider_result(snap, hw4, agent_user_id=100)
    assert result is None
    assert noise == [70]
