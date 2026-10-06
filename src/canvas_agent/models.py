"""Domain models for the Canvas discussion agent."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ControlStatus(str, Enum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    UNKNOWN = "UNKNOWN"


class PendingWriteStatus(str, Enum):
    INTENDED = "intended"
    SUBMITTED_UNKNOWN = "submitted_unknown"
    CONFIRMED = "confirmed"
    ABANDONED = "abandoned"


class WriteKind(str, Enum):
    ENTRY = "entry"
    REPLY = "reply"


class ContributionRecord(BaseModel):
    canvas_entry_id: int
    parent_id: int | None = None
    fingerprint: str
    posted_at: datetime
    verified: bool = False
    request_id: str


class PendingWrite(BaseModel):
    request_id: str
    kind: WriteKind
    parent_id: int | None = None
    message_plain: str
    fingerprint: str
    status: PendingWriteStatus = PendingWriteStatus.INTENDED
    created_at: datetime
    last_attempt_at: datetime | None = None


class AgentState(BaseModel):
    agent_user_id: int | None = None
    last_cycle_at: datetime | None = None
    consecutive_failures: int = 0
    stopped_reason: str | None = None
    post_timestamps: list[datetime] = Field(default_factory=list)
    contributions: list[ContributionRecord] = Field(default_factory=list)
    pending_writes: list[PendingWrite] = Field(default_factory=list)
    seen_entry_ids: list[int] = Field(default_factory=list)
    content_fingerprints: list[str] = Field(default_factory=list)


class DiscussionEntry(BaseModel):
    id: int
    user_id: int | None = None
    parent_id: int | None = None
    message_text: str = ""
    created_at: datetime | None = None


class DiscussionSnapshot(BaseModel):
    topic_id: int
    control_status: ControlStatus = ControlStatus.UNKNOWN
    topic_message_text: str = ""
    entries: list[DiscussionEntry] = Field(default_factory=list)


class AdvisorDecision(BaseModel):
    action: Literal["abstain", "post"]
    kind: WriteKind | None = None
    parent_id: int | None = None
    message: str | None = None
    rationale: str | None = None


class CycleResult(BaseModel):
    posted: bool = False
    dry_run: bool = False
    abstained: bool = False
    skipped_reason: str | None = None
    contribution: ContributionRecord | None = None
    error: str | None = None
