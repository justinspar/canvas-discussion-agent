"""Rolling-window rate limiting for Canvas posts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def prune_timestamps(
    timestamps: list[datetime],
    *,
    now: datetime | None = None,
    window_seconds: int = 3600,
) -> list[datetime]:
    now = now or _utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cutoff = now - timedelta(seconds=window_seconds)
    pruned: list[datetime] = []
    for ts in timestamps:
        aware = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        if aware >= cutoff:
            pruned.append(aware)
    return pruned


class RateLimiter:
    def __init__(
        self,
        *,
        max_posts: int = 3,
        window_seconds: int = 3600,
        max_per_cycle: int = 1,
    ) -> None:
        self.max_posts = max_posts
        self.window_seconds = window_seconds
        self.max_per_cycle = max_per_cycle

    def allow(
        self,
        timestamps: list[datetime],
        *,
        now: datetime | None = None,
        posts_this_cycle: int = 0,
    ) -> tuple[bool, str | None]:
        now = now or _utcnow()
        recent = prune_timestamps(
            timestamps, now=now, window_seconds=self.window_seconds
        )
        if posts_this_cycle >= self.max_per_cycle:
            return False, "per_cycle_limit"
        if len(recent) >= self.max_posts:
            return False, "rolling_window_limit"
        return True, None

    def record(
        self,
        timestamps: list[datetime],
        *,
        now: datetime | None = None,
    ) -> list[datetime]:
        now = now or _utcnow()
        recent = prune_timestamps(
            timestamps, now=now, window_seconds=self.window_seconds
        )
        recent.append(now if now.tzinfo else now.replace(tzinfo=timezone.utc))
        return recent
