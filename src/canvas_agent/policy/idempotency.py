"""Idempotency and lost-acknowledgement reconciliation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from canvas_agent.canvas.parse import content_fingerprint
from canvas_agent.models import (
    AgentState,
    ContributionRecord,
    DiscussionEntry,
    DiscussionSnapshot,
    PendingWrite,
    PendingWriteStatus,
    WriteKind,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_request_id() -> str:
    return str(uuid4())


def fingerprint_for(message: str, parent_id: int | None) -> str:
    return content_fingerprint(message, parent_id)


def is_duplicate(
    state: AgentState,
    fingerprint: str,
    *,
    snapshot: DiscussionSnapshot | None = None,
    agent_user_id: int | None = None,
) -> bool:
    if fingerprint in state.content_fingerprints:
        return True
    if any(c.fingerprint == fingerprint for c in state.contributions):
        return True
    for pending in state.pending_writes:
        if pending.fingerprint == fingerprint and pending.status in {
            PendingWriteStatus.INTENDED,
            PendingWriteStatus.SUBMITTED_UNKNOWN,
            PendingWriteStatus.CONFIRMED,
        }:
            return True
    if snapshot is not None and agent_user_id is not None:
        for entry in snapshot.entries:
            if entry.user_id != agent_user_id:
                continue
            if fingerprint_for(entry.message_text, entry.parent_id) == fingerprint:
                return True
    return False


def create_pending(
    *,
    kind: WriteKind,
    parent_id: int | None,
    message: str,
    now: datetime | None = None,
) -> PendingWrite:
    now = now or _utcnow()
    return PendingWrite(
        request_id=new_request_id(),
        kind=kind,
        parent_id=parent_id,
        message_plain=message,
        fingerprint=fingerprint_for(message, parent_id),
        status=PendingWriteStatus.INTENDED,
        created_at=now,
    )


def mark_submitted_unknown(pending: PendingWrite, now: datetime | None = None) -> PendingWrite:
    now = now or _utcnow()
    return pending.model_copy(
        update={
            "status": PendingWriteStatus.SUBMITTED_UNKNOWN,
            "last_attempt_at": now,
        }
    )


def confirm_pending(
    state: AgentState,
    pending: PendingWrite,
    *,
    canvas_entry_id: int,
    verified: bool,
    now: datetime | None = None,
) -> AgentState:
    now = now or _utcnow()
    updated_pending = [
        (
            p.model_copy(update={"status": PendingWriteStatus.CONFIRMED, "last_attempt_at": now})
            if p.request_id == pending.request_id
            else p
        )
        for p in state.pending_writes
    ]
    contribution = ContributionRecord(
        canvas_entry_id=canvas_entry_id,
        parent_id=pending.parent_id,
        fingerprint=pending.fingerprint,
        posted_at=now,
        verified=verified,
        request_id=pending.request_id,
    )
    fingerprints = list(state.content_fingerprints)
    if pending.fingerprint not in fingerprints:
        fingerprints.append(pending.fingerprint)
    seen = list(state.seen_entry_ids)
    if canvas_entry_id not in seen:
        seen.append(canvas_entry_id)
    contributions = [
        c for c in state.contributions if c.request_id != pending.request_id
    ]
    contributions.append(contribution)
    return state.model_copy(
        update={
            "pending_writes": updated_pending,
            "contributions": contributions,
            "content_fingerprints": fingerprints,
            "seen_entry_ids": seen,
        }
    )


def abandon_pending(state: AgentState, request_id: str) -> AgentState:
    updated = [
        (
            p.model_copy(update={"status": PendingWriteStatus.ABANDONED})
            if p.request_id == request_id
            else p
        )
        for p in state.pending_writes
    ]
    return state.model_copy(update={"pending_writes": updated})


def _match_own_entry(
    pending: PendingWrite,
    entries: list[DiscussionEntry],
    agent_user_id: int,
) -> DiscussionEntry | None:
    for entry in entries:
        if entry.user_id != agent_user_id:
            continue
        if fingerprint_for(entry.message_text, entry.parent_id) == pending.fingerprint:
            return entry
    return None


def reconcile_pending(
    state: AgentState,
    snapshot: DiscussionSnapshot,
    *,
    agent_user_id: int | None,
    now: datetime | None = None,
    max_age_hours: float = 6.0,
) -> AgentState:
    """Recover from lost acknowledgements by matching pending writes to Canvas."""
    now = now or _utcnow()
    if agent_user_id is None:
        return state

    current = state
    for pending in list(state.pending_writes):
        if pending.status not in {
            PendingWriteStatus.SUBMITTED_UNKNOWN,
            PendingWriteStatus.INTENDED,
        }:
            continue

        match = _match_own_entry(pending, snapshot.entries, agent_user_id)
        if match is not None:
            current = confirm_pending(
                current,
                pending,
                canvas_entry_id=match.id,
                verified=True,
                now=now,
            )
            continue

        created = pending.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = now - created
        # Only abandon intended/submitted_unknown after max age if still absent
        if pending.status is PendingWriteStatus.SUBMITTED_UNKNOWN and age > timedelta(
            hours=max_age_hours
        ):
            current = abandon_pending(current, pending.request_id)
        elif pending.status is PendingWriteStatus.INTENDED and age > timedelta(
            hours=max_age_hours
        ):
            current = abandon_pending(current, pending.request_id)

    # Sync fingerprints from any own posts already on Canvas
    fingerprints = list(current.content_fingerprints)
    seen = list(current.seen_entry_ids)
    for entry in snapshot.entries:
        if entry.id not in seen:
            seen.append(entry.id)
        if entry.user_id == agent_user_id:
            fp = fingerprint_for(entry.message_text, entry.parent_id)
            if fp not in fingerprints:
                fingerprints.append(fp)
            if not any(c.canvas_entry_id == entry.id for c in current.contributions):
                current.contributions.append(
                    ContributionRecord(
                        canvas_entry_id=entry.id,
                        parent_id=entry.parent_id,
                        fingerprint=fp,
                        posted_at=entry.created_at or now,
                        verified=True,
                        request_id=f"recovered-{entry.id}",
                    )
                )
    return current.model_copy(
        update={
            "content_fingerprints": fingerprints,
            "seen_entry_ids": seen,
        }
    )


def has_open_submitted_unknown(state: AgentState, fingerprint: str) -> bool:
    return any(
        p.fingerprint == fingerprint
        and p.status is PendingWriteStatus.SUBMITTED_UNKNOWN
        for p in state.pending_writes
    )
