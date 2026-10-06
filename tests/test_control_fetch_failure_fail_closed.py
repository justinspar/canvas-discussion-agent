"""Control-line fetch failures must fail closed (never POST)."""

from canvas_agent.canvas.client import CanvasError
from canvas_agent.cycle import CycleOrchestrator
from canvas_agent.llm.openai_advisor import StubAdvisor
from tests.conftest import FakeCanvas, make_post_decision


class ControlBoomCanvas(FakeCanvas):
    def get_control_status(self):  # type: ignore[override]
        raise CanvasError("control endpoint unavailable")


def test_control_fetch_failure_does_not_post(test_config, tmp_storage) -> None:
    canvas = ControlBoomCanvas()
    advisor = StubAdvisor(make_post_decision("Should not be posted on control failure."))
    orch = CycleOrchestrator(
        config=test_config, storage=tmp_storage, canvas=canvas, advisor=advisor
    )
    result = orch.run_once()
    assert result.posted is False
    assert result.skipped_reason == "control_fetch_failed"
    assert canvas.posts == []
