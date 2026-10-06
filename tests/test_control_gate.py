"""Control-line gate tests."""

from canvas_agent.canvas.parse import parse_control_status
from canvas_agent.cycle import CycleOrchestrator
from canvas_agent.llm.openai_advisor import StubAdvisor
from canvas_agent.models import ControlStatus
from canvas_agent.safety.control import may_post
from tests.conftest import FakeCanvas, load_fixture, make_post_decision


def test_parse_control_running_and_paused() -> None:
    running = load_fixture("topic_running.json")["message"]
    paused = load_fixture("topic_paused.json")["message"]
    assert parse_control_status(running) is ControlStatus.RUNNING
    assert parse_control_status(paused) is ControlStatus.PAUSED
    assert parse_control_status("<p>no control here</p>") is ControlStatus.UNKNOWN
    assert parse_control_status("") is ControlStatus.UNKNOWN


def test_may_post_only_when_running() -> None:
    assert may_post(ControlStatus.RUNNING) is True
    assert may_post(ControlStatus.PAUSED) is False
    assert may_post(ControlStatus.UNKNOWN) is False


def test_cycle_blocks_when_paused(test_config, tmp_storage) -> None:
    canvas = FakeCanvas(topic=load_fixture("topic_paused.json"))
    advisor = StubAdvisor(make_post_decision())
    orch = CycleOrchestrator(
        config=test_config, storage=tmp_storage, canvas=canvas, advisor=advisor
    )
    result = orch.run_once()
    assert result.posted is False
    assert result.skipped_reason == "control_paused"
    assert canvas.posts == []


def test_cycle_blocks_when_control_unknown(test_config, tmp_storage) -> None:
    topic = {"id": 448963, "message": "<p>Something else</p>"}
    canvas = FakeCanvas(topic=topic)
    advisor = StubAdvisor(make_post_decision())
    orch = CycleOrchestrator(
        config=test_config, storage=tmp_storage, canvas=canvas, advisor=advisor
    )
    result = orch.run_once()
    assert result.posted is False
    assert result.skipped_reason == "control_unknown"
    assert canvas.posts == []
