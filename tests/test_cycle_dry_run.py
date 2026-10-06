"""Dry-run cycle performs full logic but never writes."""

from dataclasses import replace

from canvas_agent.cycle import CycleOrchestrator
from canvas_agent.llm.openai_advisor import StubAdvisor
from tests.conftest import FakeCanvas, make_post_decision


def test_cycle_dry_run_never_posts(test_config, tmp_storage) -> None:
    dry = replace(test_config, dry_run=True)
    canvas = FakeCanvas()
    advisor = StubAdvisor(make_post_decision("Would-be post in dry run."))
    orch = CycleOrchestrator(
        config=dry, storage=tmp_storage, canvas=canvas, advisor=advisor
    )
    result = orch.run_once()
    assert result.dry_run is True
    assert result.posted is False
    assert result.skipped_reason == "dry_run"
    assert canvas.posts == []
    assert advisor.calls == 1
