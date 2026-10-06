"""Lost-acknowledgement recovery: Canvas accepted write, client never got response."""

from canvas_agent.cycle import CycleOrchestrator
from canvas_agent.llm.openai_advisor import StubAdvisor
from canvas_agent.models import AdvisorDecision, PendingWriteStatus
from canvas_agent.policy.idempotency import fingerprint_for
from tests.conftest import FakeCanvas, make_post_decision


def test_recovery_from_lost_acknowledgement(test_config, tmp_storage) -> None:
    message = "Unique contribution about calibration of LLM judges."
    canvas = FakeCanvas(fail_ack_once=True)
    advisor = StubAdvisor(make_post_decision(message))

    orch = CycleOrchestrator(
        config=test_config, storage=tmp_storage, canvas=canvas, advisor=advisor
    )

    # Cycle 1: POST succeeds on server-side fake, client sees transient error
    first = orch.run_once()
    assert first.posted is False
    assert first.skipped_reason == "lost_ack_pending"
    assert len(canvas.posts) == 1  # accepted server-side

    state = tmp_storage.load()
    pending = [p for p in state.pending_writes if p.status is PendingWriteStatus.SUBMITTED_UNKNOWN]
    assert len(pending) == 1
    assert pending[0].fingerprint == fingerprint_for(message, None)

    # Cycle 2: same advisor proposal, but reconcile should find the post and skip duplicate
    second = orch.run_once()
    assert second.posted is False
    # Either abstain-after-reconcile duplicate, or duplicate skip
    assert second.skipped_reason in {"duplicate", "abstain"} or second.abstained
    assert len(canvas.posts) == 1  # no second POST

    state = tmp_storage.load()
    assert any(c.verified for c in state.contributions)
    assert fingerprint_for(message, None) in state.content_fingerprints
    assert not any(
        p.status is PendingWriteStatus.SUBMITTED_UNKNOWN for p in state.pending_writes
    )


def test_lost_ack_then_abstain_still_records_contribution(test_config, tmp_storage) -> None:
    message = "Another unique lost-ack message about rubric design."
    canvas = FakeCanvas(fail_ack_once=True)
    advisor = StubAdvisor(make_post_decision(message))
    orch = CycleOrchestrator(
        config=test_config, storage=tmp_storage, canvas=canvas, advisor=advisor
    )
    orch.run_once()

    # Next cycle: advisor abstains; reconcile should still confirm the pending write
    advisor.decision = AdvisorDecision(action="abstain", rationale="nothing new")
    result = orch.run_once()
    assert result.abstained is True
    assert len(canvas.posts) == 1
    state = tmp_storage.load()
    assert any(
        c.fingerprint == fingerprint_for(message, None) and c.verified
        for c in state.contributions
    )
