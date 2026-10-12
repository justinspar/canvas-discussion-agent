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


class OfferStatus(str, Enum):
    NEEDED = "needed"
    POSTED = "posted"
    VERIFIED = "verified"


class DelegationStatus(str, Enum):
    NONE = "none"
    REQUESTED = "requested"
    AWAITING = "awaiting"
    VERIFYING = "verifying"
    AWAITING_CORRECTION = "awaiting_correction"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    PROVIDER_DECLINED = "provider_declined"


class IncomingRequestStatus(str, Enum):
    SEEN = "seen"
    CLARIFY_SENT = "clarify_sent"
    COMPLETED = "completed"
    IGNORED = "ignored"


class ProviderCandidate(BaseModel):
    entry_id: int
    user_id: int | None = None
    score: float = 0.0
    reason: str = ""
    title_snippet: str = ""
    offer_excerpt: str = ""


class IncomingRequestRecord(BaseModel):
    request_entry_id: int
    parent_offer_id: int
    status: IncomingRequestStatus = IncomingRequestStatus.SEEN
    content_hash: str = ""
    response_entry_id: int | None = None
    clarification_entry_id: int | None = None
    summary: str = ""


class VerificationRecord(BaseModel):
    result_entry_id: int
    method: str
    outcome: str
    accepted: bool = False
    evidence: str = ""
    checked_at: datetime | None = None


class AcceptedWorkRecord(BaseModel):
    result_entry_id: int
    incorporated_path: str = ""
    reason: str = ""
    used_at: datetime | None = None


class TipRecord(BaseModel):
    amount: int = 0
    reason: str = ""
    reply_entry_id: int | None = None
    recorded_at: datetime | None = None


class Hw4State(BaseModel):
    """Homework 4 agent-services state (nested under AgentState)."""

    offer_entry_id: int | None = None
    offer_fingerprint: str | None = None
    offer_status: OfferStatus = OfferStatus.NEEDED
    offer_verified: bool = False
    offer_clarification_id: int | None = None

    incoming_requests: list[IncomingRequestRecord] = Field(default_factory=list)

    candidate_providers: list[ProviderCandidate] = Field(default_factory=list)
    selected_provider_entry_id: int | None = None
    selected_provider_user_id: int | None = None
    rejected_provider_entry_ids: list[int] = Field(default_factory=list)
    provider_rediscoveries: int = 0

    delegated_request_id: str | None = None
    request_reply_id: int | None = None
    request_hash: str | None = None
    task_description: str | None = None
    acceptance_criteria: str | None = None
    request_deadline: datetime | None = None
    delegation_status: DelegationStatus = DelegationStatus.NONE

    provider_results_seen: list[int] = Field(default_factory=list)
    verification_results: list[VerificationRecord] = Field(default_factory=list)
    correction_request_id: str | None = None
    correction_reply_id: int | None = None
    accepted_work: AcceptedWorkRecord | None = None
    acknowledgment_id: int | None = None
    tip: TipRecord | None = None

    last_phase: str | None = None


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
    hw4: Hw4State = Field(default_factory=Hw4State)


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
    # Evidence fields for graders / last_cycle.json
    action: Literal["abstain", "post", "skip", "error"] | None = None
    kind: WriteKind | None = None
    parent_id: int | None = None
    rationale: str | None = None
    hw4_phase: str | None = None
    hw4_verification_outcome: str | None = None
