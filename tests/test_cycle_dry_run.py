"""Dry-run cycle performs full logic but never writes."""

from dataclasses import replace

from canvas_agent.cycle import CycleOrchestrator
from tests.conftest import FakeCanvas, make_agentic_advisor, make_post_decision


def test_cycle_dry_run_never_posts(test_config, tmp_storage) -> None:
    dry = replace(test_config, dry_run=True)
    canvas = FakeCanvas()
    advisor = make_agentic_advisor(
        make_post_decision("Would-be post in dry run."), intent="other"
    )
    orch = CycleOrchestrator(
        config=dry, storage=tmp_storage, canvas=canvas, advisor=advisor
    )
    result = orch.run_once()
    assert result.dry_run is True
    assert result.posted is False
    assert result.skipped_reason == "dry_run"
    assert canvas.posts == []
