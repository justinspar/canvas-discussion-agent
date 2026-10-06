"""JSON storage round-trip and atomicity basics."""

from datetime import datetime, timezone

from canvas_agent.models import AgentState, ContributionRecord
from canvas_agent.storage.json_store import JsonFileStorage


def test_json_store_roundtrip(tmp_path) -> None:
    store = JsonFileStorage(tmp_path / "agent_state.json")
    empty = store.load()
    assert empty.agent_user_id is None

    state = AgentState(
        agent_user_id=100,
        consecutive_failures=1,
        content_fingerprints=["abc"],
        contributions=[
            ContributionRecord(
                canvas_entry_id=9,
                parent_id=None,
                fingerprint="abc",
                posted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                verified=True,
                request_id="req-1",
            )
        ],
    )
    store.save(state)
    loaded = store.load()
    assert loaded.agent_user_id == 100
    assert loaded.content_fingerprints == ["abc"]
    assert loaded.contributions[0].canvas_entry_id == 9
    assert loaded.contributions[0].verified is True
