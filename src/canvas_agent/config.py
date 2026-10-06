"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from canvas_agent.llm.openai_advisor import DEFAULT_PARLEY_BASE_URL, DEFAULT_PARLEY_MODEL


def _normalize_parley_base(url: str) -> str:
    """Ensure OpenAI-compatible clients hit .../v1."""
    base = url.rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


@dataclass(frozen=True)
class Config:
    canvas_base_url: str
    canvas_token: str
    course_id: int
    topic_id: int
    dry_run: bool
    interval_hours: float
    max_consecutive_failures: int
    max_posts_per_hour: int
    rate_limit_window_seconds: int
    llm_api_key: str | None
    llm_model: str
    llm_base_url: str
    state_path: Path
    lock_path: Path
    pending_max_age_hours: float

    @classmethod
    def from_env(cls, *, dry_run: bool | None = None) -> Config:
        token = os.environ.get("CANVAS_TOKEN", "").strip()
        if not token:
            raise ValueError("CANVAS_TOKEN environment variable is required")

        root = Path(os.environ.get("CANVAS_AGENT_DATA_DIR", "data"))
        env_dry = os.environ.get("CANVAS_AGENT_DRY_RUN", "0").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        # Prefer PARLEY_API_KEY; accept OPENAI_API_KEY / ANTHROPIC_API_KEY as aliases
        # for convenience when the Parley key was pasted into those fields.
        llm_key = (
            os.environ.get("PARLEY_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or None
        )
        if llm_key:
            llm_key = llm_key.strip() or None

        return cls(
            canvas_base_url=os.environ.get(
                "CANVAS_BASE_URL", "https://canvas.mit.edu"
            ).rstrip("/"),
            canvas_token=token,
            course_id=int(os.environ.get("CANVAS_COURSE_ID", "40577")),
            topic_id=int(os.environ.get("CANVAS_TOPIC_ID", "448963")),
            dry_run=env_dry if dry_run is None else dry_run,
            interval_hours=float(os.environ.get("CANVAS_AGENT_INTERVAL_HOURS", "3")),
            max_consecutive_failures=int(
                os.environ.get("CANVAS_AGENT_MAX_FAILURES", "3")
            ),
            max_posts_per_hour=int(os.environ.get("CANVAS_AGENT_MAX_POSTS_HOUR", "3")),
            rate_limit_window_seconds=int(
                os.environ.get("CANVAS_AGENT_RATE_WINDOW_SEC", "3600")
            ),
            llm_api_key=llm_key,
            llm_model=os.environ.get("PARLEY_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or DEFAULT_PARLEY_MODEL,
            llm_base_url=_normalize_parley_base(
                os.environ.get("PARLEY_BASE_URL")
                or os.environ.get("ANTHROPIC_BASE_URL")
                or os.environ.get("OPENAI_BASE_URL")
                or DEFAULT_PARLEY_BASE_URL
            ),
            state_path=root / "agent_state.json",
            lock_path=root / "agent.lock",
            pending_max_age_hours=float(
                os.environ.get("CANVAS_AGENT_PENDING_MAX_AGE_HOURS", "6")
            ),
        )

    def __repr__(self) -> str:
        return (
            f"Config(canvas_base_url={self.canvas_base_url!r}, "
            f"course_id={self.course_id}, topic_id={self.topic_id}, "
            f"dry_run={self.dry_run}, llm_model={self.llm_model!r}, "
            f"canvas_token=***REDACTED***)"
        )
