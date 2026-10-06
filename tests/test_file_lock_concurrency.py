"""Local file-lock overlap protection."""

from pathlib import Path

from canvas_agent.scheduler import FileLock


def test_second_acquire_fails_while_held(tmp_path: Path) -> None:
    lock_path = tmp_path / "agent.lock"
    first = FileLock(lock_path)
    second = FileLock(lock_path)
    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()
    assert second.acquire() is True
    second.release()
