"""Verify successful contribution is read back from Canvas."""

from canvas_agent.cycle import CycleOrchestrator
from canvas_agent.llm.openai_advisor import StubAdvisor
from tests.conftest import FakeCanvas, make_post_decision


def test_successful_post_is_verified(test_config, tmp_storage) -> None:
    canvas = FakeCanvas()
    advisor = StubAdvisor(make_post_decision("Verified contribution on measurement error."))
    orch = CycleOrchestrator(
        config=test_config, storage=tmp_storage, canvas=canvas, advisor=advisor
    )
    result = orch.run_once()
    assert result.posted is True
    assert result.contribution is not None
    assert result.contribution.verified is True
    assert len(canvas.posts) == 1


def test_missing_readback_marks_unverified(test_config, tmp_storage) -> None:
    canvas = FakeCanvas()

    original_verify = canvas.verify_entry

    def missing_verify(_entry_id: int):
        return None

    canvas.verify_entry = missing_verify  # type: ignore[method-assign]
    advisor = StubAdvisor(make_post_decision("Post that cannot be read back."))
    orch = CycleOrchestrator(
        config=test_config, storage=tmp_storage, canvas=canvas, advisor=advisor
    )
    result = orch.run_once()
    assert result.posted is True
    assert result.skipped_reason == "unverified"
    assert result.contribution is not None
    assert result.contribution.verified is False
    # restore for clarity
    canvas.verify_entry = original_verify  # type: ignore[method-assign]
