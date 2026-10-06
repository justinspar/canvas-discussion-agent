"""Safe stop after consecutive cycle failures."""

from canvas_agent.cycle import CycleOrchestrator
from canvas_agent.llm.openai_advisor import StubAdvisor
from canvas_agent.models import AdvisorDecision
from tests.conftest import FakeCanvas, make_post_decision


class BoomCanvas(FakeCanvas):
    def get_discussion_view(self):  # type: ignore[override]
        raise RuntimeError("simulated read failure")


def test_retry_exhaustion_sets_safe_stop(test_config, tmp_storage) -> None:
    canvas = BoomCanvas()
    advisor = StubAdvisor(make_post_decision("should never post"))
    orch = CycleOrchestrator(
        config=test_config, storage=tmp_storage, canvas=canvas, advisor=advisor
    )

    for _ in range(test_config.max_consecutive_failures):
        result = orch.run_once()
        assert result.error

    state = tmp_storage.load()
    assert state.stopped_reason == "max_failures"
    assert state.consecutive_failures >= test_config.max_consecutive_failures

    blocked = orch.run_once()
    assert blocked.skipped_reason == "stopped:max_failures"
    assert canvas.posts == []
