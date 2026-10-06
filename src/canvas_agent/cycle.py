"""One scheduled cycle of the Canvas discussion agent."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from canvas_agent.canvas.client import (
    CanvasAmbiguousWriteError,
    CanvasClient,
    CanvasError,
    CanvasTransientError,
)
from canvas_agent.config import Config
from canvas_agent.evidence import write_cycle_evidence
from canvas_agent.llm.protocol import LLMAdvisor
from canvas_agent.logging_utils import redact
from canvas_agent.models import (
    AgentState,
    CycleResult,
    DiscussionSnapshot,
    WriteKind,
)
from canvas_agent.policy.idempotency import (
    abandon_pending,
    confirm_pending,
    create_pending,
    fingerprint_for,
    is_duplicate,
    mark_submitted_unknown,
    reconcile_pending,
)
from canvas_agent.policy.rate_limit import RateLimiter
from canvas_agent.safety.control import explain_block, may_post
from canvas_agent.safety.output_guard import OutputGuardError, validate_decision
from canvas_agent.storage.protocol import StorageProtocol

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CycleOrchestrator:
    def __init__(
        self,
        *,
        config: Config,
        storage: StorageProtocol,
        canvas: CanvasClient,
        advisor: LLMAdvisor,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.config = config
        self.storage = storage
        self.canvas = canvas
        self.advisor = advisor
        self.rate_limiter = rate_limiter or RateLimiter(
            max_posts=config.max_posts_per_hour,
            window_seconds=config.rate_limit_window_seconds,
            max_per_cycle=1,
        )

    def _evidence_path(self) -> Path:
        return self.config.state_path.parent / "last_cycle.json"

    def _record_evidence(self, result: CycleResult) -> CycleResult:
        try:
            write_cycle_evidence(self._evidence_path(), result)
        except OSError as exc:
            logger.warning("Could not write cycle evidence: %s", type(exc).__name__)
        return result

    def run_once(self) -> CycleResult:
        state = self.storage.load()
        if state.stopped_reason:
            return self._record_evidence(
                CycleResult(
                    skipped_reason=f"stopped:{state.stopped_reason}",
                    action="skip",
                )
            )

        try:
            result = self._run_cycle(state)
            state = self.storage.load()
            state.consecutive_failures = 0
            state.last_cycle_at = _utcnow()
            self.storage.save(state)
            return self._record_evidence(result)
        except Exception as exc:
            logger.exception("Cycle failed: %s", type(exc).__name__)
            state = self.storage.load()
            state.consecutive_failures += 1
            state.last_cycle_at = _utcnow()
            if state.consecutive_failures >= self.config.max_consecutive_failures:
                state.stopped_reason = "max_failures"
                logger.error(
                    "Stopping after %s consecutive failures",
                    state.consecutive_failures,
                )
            self.storage.save(state)
            secrets = [self.config.canvas_token, self.config.llm_api_key or ""]
            return self._record_evidence(
                CycleResult(
                    error=redact(str(exc), secrets),
                    action="error",
                )
            )

    def _peer_parent(
        self,
        snapshot: DiscussionSnapshot,
        parent_id: int | None,
        agent_user_id: int | None,
    ) -> tuple[bool, str | None, int | None]:
        """Return (ok, skip_reason, parent_user_id)."""
        if parent_id is None:
            return False, "invalid_parent_id", None
        parent = next((e for e in snapshot.entries if e.id == parent_id), None)
        if parent is None:
            return False, "invalid_parent_id", None
        if agent_user_id is not None and parent.user_id == agent_user_id:
            return False, "reply_to_self", parent.user_id
        return True, None, parent.user_id

    def _run_cycle(self, state: AgentState) -> CycleResult:
        # Resolve agent identity
        if state.agent_user_id is None:
            state.agent_user_id = self.canvas.get_self_user_id()
            self.storage.save(state)

        snapshot = self.canvas.get_discussion_view()
        state = reconcile_pending(
            state,
            snapshot,
            agent_user_id=state.agent_user_id,
            max_age_hours=self.config.pending_max_age_hours,
        )
        # Refresh seen ids
        for entry in snapshot.entries:
            if entry.id not in state.seen_entry_ids:
                state.seen_entry_ids.append(entry.id)
        self.storage.save(state)

        prior_messages = [c.fingerprint[:12] for c in state.contributions]
        own_texts = [
            e.message_text
            for e in snapshot.entries
            if e.user_id == state.agent_user_id and e.message_text
        ]

        decision = self.advisor.decide_and_draft(
            snapshot,
            agent_user_id=state.agent_user_id,
            prior_fingerprints=list(state.content_fingerprints),
            prior_messages=own_texts or prior_messages,
        )

        try:
            decision = validate_decision(decision)
        except OutputGuardError as exc:
            logger.info("Advisor output rejected: %s", exc)
            return CycleResult(
                abstained=True,
                skipped_reason=f"invalid_draft:{exc}",
                action="abstain",
                rationale=str(exc),
            )

        if decision.action == "abstain":
            logger.info("Abstaining: %s", decision.rationale)
            return CycleResult(
                abstained=True,
                skipped_reason="abstain",
                action="abstain",
                rationale=decision.rationale,
            )

        assert decision.kind is not None and decision.message is not None

        parent_user_id: int | None = None
        if decision.kind is WriteKind.REPLY:
            ok, skip, parent_user_id = self._peer_parent(
                snapshot, decision.parent_id, state.agent_user_id
            )
            if not ok:
                return CycleResult(
                    abstained=True,
                    skipped_reason=skip,
                    action="skip",
                    kind=decision.kind,
                    parent_id=decision.parent_id,
                    rationale=decision.rationale,
                )

        allowed, reason = self.rate_limiter.allow(state.post_timestamps)
        if not allowed:
            logger.info("Rate limited: %s", reason)
            return CycleResult(
                skipped_reason=reason,
                action="skip",
                kind=decision.kind,
                parent_id=decision.parent_id,
                rationale=decision.rationale,
            )

        fp = fingerprint_for(decision.message, decision.parent_id)
        if is_duplicate(
            state,
            fp,
            snapshot=snapshot,
            agent_user_id=state.agent_user_id,
        ):
            return CycleResult(
                skipped_reason="duplicate",
                action="skip",
                kind=decision.kind,
                parent_id=decision.parent_id,
                rationale=decision.rationale,
            )

        pending = create_pending(
            kind=decision.kind,
            parent_id=decision.parent_id,
            message=decision.message,
        )
        state.pending_writes.append(pending)
        self.storage.save(state)

        # Fresh control-line check immediately before EVERY write
        try:
            control_status, _ = self.canvas.get_control_status()
        except CanvasError as exc:
            logger.warning(
                "Control-line fetch failed closed: %s", type(exc).__name__
            )
            state = abandon_pending(self.storage.load(), pending.request_id)
            self.storage.save(state)
            return CycleResult(
                skipped_reason="control_fetch_failed",
                action="skip",
                kind=decision.kind,
                parent_id=decision.parent_id,
                rationale=decision.rationale,
            )

        if not may_post(control_status):
            block = explain_block(control_status)
            logger.info("Write blocked by control gate: %s", block)
            state = abandon_pending(self.storage.load(), pending.request_id)
            self.storage.save(state)
            return CycleResult(
                skipped_reason=block,
                action="skip",
                kind=decision.kind,
                parent_id=decision.parent_id,
                rationale=decision.rationale,
            )

        if self.config.dry_run:
            logger.info(
                "Dry-run: would post %s parent=%s parent_user_id=%s",
                pending.kind,
                pending.parent_id,
                parent_user_id,
            )
            state = abandon_pending(self.storage.load(), pending.request_id)
            self.storage.save(state)
            return CycleResult(
                dry_run=True,
                skipped_reason="dry_run",
                posted=False,
                action="post",
                kind=decision.kind,
                parent_id=decision.parent_id,
                rationale=decision.rationale,
            )

        # Mark submitted_unknown BEFORE the POST so a crash mid-flight is recoverable
        state = self.storage.load()
        updated_pending = []
        current_pending = pending
        for p in state.pending_writes:
            if p.request_id == pending.request_id:
                current_pending = mark_submitted_unknown(p)
                updated_pending.append(current_pending)
            else:
                updated_pending.append(p)
        state.pending_writes = updated_pending
        self.storage.save(state)

        # Re-check control immediately before the HTTP write (fail closed).
        try:
            control_status, _ = self.canvas.get_control_status()
        except CanvasError:
            logger.warning("Pre-write control fetch failed; aborting POST")
            state = abandon_pending(self.storage.load(), current_pending.request_id)
            self.storage.save(state)
            return CycleResult(
                skipped_reason="control_fetch_failed",
                action="skip",
                kind=decision.kind,
                parent_id=decision.parent_id,
                rationale=decision.rationale,
            )
        if not may_post(control_status):
            block = explain_block(control_status)
            logger.info("Pre-write control gate blocked POST: %s", block)
            state = abandon_pending(self.storage.load(), current_pending.request_id)
            self.storage.save(state)
            return CycleResult(
                skipped_reason=block,
                action="skip",
                kind=decision.kind,
                parent_id=decision.parent_id,
                rationale=decision.rationale,
            )

        try:
            if current_pending.kind is WriteKind.ENTRY:
                created = self.canvas.create_entry(current_pending.message_plain)
            else:
                assert current_pending.parent_id is not None
                logger.info(
                    "Posting reply parent_id=%s parent_user_id=%s",
                    current_pending.parent_id,
                    parent_user_id,
                )
                created = self.canvas.create_reply(
                    current_pending.parent_id, current_pending.message_plain
                )
            entry_id = int(created["id"])
        except (CanvasAmbiguousWriteError, CanvasTransientError):
            logger.warning(
                "Write may have succeeded but ack was lost (request_id=%s)",
                current_pending.request_id,
            )
            return CycleResult(
                skipped_reason="lost_ack_pending",
                action="skip",
                kind=decision.kind,
                parent_id=decision.parent_id,
                rationale=decision.rationale,
            )
        except CanvasError as exc:
            logger.error("Canvas write failed: %s", type(exc).__name__)
            state = abandon_pending(self.storage.load(), current_pending.request_id)
            self.storage.save(state)
            raise

        verified_payload = self.canvas.verify_entry(entry_id)
        verified = verified_payload is not None
        state = self.storage.load()
        pending_now = next(
            p for p in state.pending_writes if p.request_id == current_pending.request_id
        )
        state = confirm_pending(
            state, pending_now, canvas_entry_id=entry_id, verified=verified
        )
        state.post_timestamps = self.rate_limiter.record(state.post_timestamps)
        self.storage.save(state)

        contribution = next(
            c for c in state.contributions if c.request_id == current_pending.request_id
        )
        if not verified:
            logger.warning("Post created but verification failed for entry %s", entry_id)
            return CycleResult(
                posted=True,
                contribution=contribution,
                skipped_reason="unverified",
                action="post",
                kind=decision.kind,
                parent_id=decision.parent_id,
                rationale=decision.rationale,
            )

        logger.info("Posted and verified entry_id=%s", entry_id)
        return CycleResult(
            posted=True,
            contribution=contribution,
            action="post",
            kind=decision.kind,
            parent_id=decision.parent_id,
            rationale=decision.rationale,
        )
