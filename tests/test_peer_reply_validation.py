"""Peer-linked replies: allow other agents, block reply-to-self."""

from canvas_agent.cycle import CycleOrchestrator
from canvas_agent.llm.openai_advisor import StubAdvisor
from canvas_agent.models import WriteKind
from tests.conftest import FakeCanvas, make_post_decision


def test_reply_to_self_is_blocked(test_config, tmp_storage) -> None:
    # Entry id 2 in fixture is authored by agent user_id=100
    canvas = FakeCanvas()
    advisor = StubAdvisor(
        make_post_decision(
            "Replying to my own prior message should be rejected.",
            kind=WriteKind.REPLY,
            parent_id=2,
        )
    )
    orch = CycleOrchestrator(
        config=test_config, storage=tmp_storage, canvas=canvas, advisor=advisor
    )
    result = orch.run_once()
    assert result.posted is False
    assert result.skipped_reason == "reply_to_self"
    assert canvas.posts == []


def test_reply_to_peer_is_allowed_in_dry_run(test_config, tmp_storage) -> None:
    from dataclasses import replace

    dry = replace(test_config, dry_run=True)
    canvas = FakeCanvas()
    # Entry id 1 is authored by user_id=200 (peer)
    advisor = StubAdvisor(
        make_post_decision(
            "Adding a concrete follow-up on evaluation independence.",
            kind=WriteKind.REPLY,
            parent_id=1,
        )
    )
    orch = CycleOrchestrator(
        config=dry, storage=tmp_storage, canvas=canvas, advisor=advisor
    )
    result = orch.run_once()
    assert result.dry_run is True
    assert result.kind is WriteKind.REPLY
    assert result.parent_id == 1
    assert result.action == "post"
    assert canvas.posts == []
    evidence = dry.state_path.parent / "last_cycle.json"
    assert evidence.exists()
    text = evidence.read_text(encoding="utf-8")
    assert '"parent_id": 1' in text
    assert '"kind": "reply"' in text
