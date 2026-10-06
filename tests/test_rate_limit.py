"""Rate limiter tests."""

from datetime import datetime, timedelta, timezone

from canvas_agent.cycle import CycleOrchestrator
from canvas_agent.llm.openai_advisor import StubAdvisor
from canvas_agent.policy.rate_limit import RateLimiter
from tests.conftest import FakeCanvas, make_post_decision


def test_fourth_post_inside_window_blocked() -> None:
    limiter = RateLimiter(max_posts=3, window_seconds=3600, max_per_cycle=1)
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    stamps = [
        now - timedelta(minutes=50),
        now - timedelta(minutes=40),
        now - timedelta(minutes=10),
    ]
    allowed, reason = limiter.allow(stamps, now=now)
    assert allowed is False
    assert reason == "rolling_window_limit"


def test_posts_outside_window_allowed() -> None:
    limiter = RateLimiter(max_posts=3, window_seconds=3600, max_per_cycle=1)
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    stamps = [
        now - timedelta(hours=2),
        now - timedelta(hours=3),
        now - timedelta(hours=4),
    ]
    allowed, reason = limiter.allow(stamps, now=now)
    assert allowed is True
    assert reason is None


def test_cycle_respects_rate_limit(test_config, tmp_storage) -> None:
    now = datetime.now(timezone.utc)
    state = tmp_storage.load()
    state.post_timestamps = [now, now, now]
    tmp_storage.save(state)

    canvas = FakeCanvas()
    advisor = StubAdvisor(make_post_decision("Fresh idea that should be rate-limited."))
    orch = CycleOrchestrator(
        config=test_config, storage=tmp_storage, canvas=canvas, advisor=advisor
    )
    result = orch.run_once()
    assert result.posted is False
    assert result.skipped_reason == "rolling_window_limit"
    assert canvas.posts == []
