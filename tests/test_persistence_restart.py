"""Persistence across simulated process restarts (durable JsonFileStorage)."""

from canvas_agent.cycle import CycleOrchestrator
from canvas_agent.llm.openai_advisor import StubAdvisor
from canvas_agent.models import AdvisorDecision, PendingWriteStatus
from canvas_agent.policy.idempotency import fingerprint_for
from canvas_agent.storage.json_store import JsonFileStorage
from tests.conftest import FakeCanvas, make_post_decision


def test_persistence_across_restart_lost_ack(test_config, tmp_path) -> None:
    state_path = tmp_path / "agent_state.json"
    storage = JsonFileStorage(state_path)
    message = "Persistent unique point about verification independence."
    canvas = FakeCanvas(fail_ack_once=True)
    advisor = StubAdvisor(make_post_decision(message))

    orch1 = CycleOrchestrator(
        config=test_config, storage=storage, canvas=canvas, advisor=advisor
    )
    first = orch1.run_once()
    assert first.skipped_reason == "lost_ack_pending"
    assert len(canvas.posts) == 1

    # Simulate process exit / new runner: fresh orchestrator, same durable file
    storage2 = JsonFileStorage(state_path)
    advisor2 = StubAdvisor(make_post_decision(message))
    orch2 = CycleOrchestrator(
        config=test_config, storage=storage2, canvas=canvas, advisor=advisor2
    )
    second = orch2.run_once()
    assert len(canvas.posts) == 1
    assert second.skipped_reason in {"duplicate", "abstain"} or second.abstained

    reloaded = storage2.load()
    assert fingerprint_for(message, None) in reloaded.content_fingerprints
    assert any(c.verified for c in reloaded.contributions)
    assert not any(
        p.status is PendingWriteStatus.SUBMITTED_UNKNOWN for p in reloaded.pending_writes
    )
