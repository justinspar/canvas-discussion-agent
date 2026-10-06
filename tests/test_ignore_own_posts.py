"""Own posts are ignored for advisor context and not duplicated."""

from canvas_agent.cycle import CycleOrchestrator
from canvas_agent.llm.openai_advisor import StubAdvisor
from canvas_agent.models import WriteKind
from canvas_agent.safety.sanitize import format_discussion_for_llm
from tests.conftest import FakeCanvas, load_fixture, make_post_decision


def test_format_excludes_own_posts() -> None:
    canvas = FakeCanvas(view=load_fixture("discussion_view.json"))
    snapshot = canvas.get_discussion_view()
    block = format_discussion_for_llm(snapshot, agent_user_id=100, exclude_own=True)
    assert "Prior agent reply" not in block
    assert "evaluation" in block.casefold()


def test_cycle_does_not_repost_existing_own_content(test_config, tmp_storage) -> None:
    canvas = FakeCanvas()
    advisor = StubAdvisor(
        make_post_decision(
            "Prior agent reply", kind=WriteKind.REPLY, parent_id=1
        )
    )
    orch = CycleOrchestrator(
        config=test_config, storage=tmp_storage, canvas=canvas, advisor=advisor
    )
    result = orch.run_once()
    assert result.posted is False
    assert result.skipped_reason == "duplicate"
    assert canvas.posts == []
