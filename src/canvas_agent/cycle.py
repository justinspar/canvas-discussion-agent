"""One scheduled cycle of the Canvas discussion agent."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from canvas_agent.canvas.client import (
    CanvasAmbiguousWriteError,
    CanvasClient,
    CanvasError,
    CanvasTransientError,
)
from canvas_agent.config import Config
from canvas_agent.llm.protocol import LLMAdvisor
from canvas_agent.logging_utils import redact
from canvas_agent.models import (
    AgentState,
    CycleResult,
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

    def run_once(self) -> CycleResult:
        state = self.storage.load()
        if state.stopped_reason:
            return CycleResult(skipped_reason=f"stopped:{state.stopped_reason}")

        try:
            result = self._run_cycle(state)
            state = self.storage.load()
            state.consecutive_failures = 0
            state.last_cycle_at = _utcnow()
            self.storage.save(state)
            return result
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
            return CycleResult(error=redact(str(exc), secrets))

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

        prior_messages = [
            c.fingerprint[:12] for c in state.contributions
        ]  # compact; full text from pending if needed
        # Prefer actual prior message text from pending confirmed / contributions via snapshot
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
            return CycleResult(abstained=True, skipped_reason=f"invalid_draft:{exc}")

        if decision.action == "abstain":
            logger.info("Abstaining: %s", decision.rationale)
            return CycleResult(abstained=True, skipped_reason="abstain")

        assert decision.kind is not None and decision.message is not None

        # Validate reply parent exists and is not ourselves-only target weirdness
        if decision.kind is WriteKind.REPLY:
            parent_ids = {e.id for e in snapshot.entries}
            if decision.parent_id not in parent_ids:
                return CycleResult(
                    abstained=True, skipped_reason="invalid_parent_id"
                )

        allowed, reason = self.rate_limiter.allow(state.post_timestamps)
        if not allowed:
            logger.info("Rate limited: %s", reason)
            return CycleResult(skipped_reason=reason)

        fp = fingerprint_for(decision.message, decision.parent_id)
        if is_duplicate(
            state,
            fp,
            snapshot=snapshot,
            agent_user_id=state.agent_user_id,
        ):
            return CycleResult(skipped_reason="duplicate")

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
            return CycleResult(skipped_reason="control_fetch_failed")

        if not may_post(control_status):
            block = explain_block(control_status)
            logger.info("Write blocked by control gate: %s", block)
            state = abandon_pending(self.storage.load(), pending.request_id)
            # For PAUSED/UNKNOWN we abandon the intent so we don't sticky-block forever
            self.storage.save(state)
            return CycleResult(skipped_reason=block)

        if self.config.dry_run:
            logger.info("Dry-run: would post %s parent=%s", pending.kind, pending.parent_id)
            state = abandon_pending(self.storage.load(), pending.request_id)
            # Keep fingerprint so dry-run doesn't propose the exact same text forever?
            # Plan: dry-run does not write; do not pollute fingerprints as confirmed.
            self.storage.save(state)
            return CycleResult(
                dry_run=True,
                skipped_reason="dry_run",
                posted=False,
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

        try:
            if current_pending.kind is WriteKind.ENTRY:
                created = self.canvas.create_entry(current_pending.message_plain)
            else:
                assert current_pending.parent_id is not None
                created = self.canvas.create_reply(
                    current_pending.parent_id, current_pending.message_plain
                )
            entry_id = int(created["id"])
        except (CanvasAmbiguousWriteError, CanvasTransientError):
            # Lost acknowledgement / ambiguous write: leave submitted_unknown
            logger.warning(
                "Write may have succeeded but ack was lost (request_id=%s)",
                current_pending.request_id,
            )
            return CycleResult(skipped_reason="lost_ack_pending")
        except CanvasError as exc:
            logger.error("Canvas write failed: %s", type(exc).__name__)
            state = abandon_pending(self.storage.load(), current_pending.request_id)
            self.storage.save(state)
            raise

        # Verify readback
        verified_payload = self.canvas.verify_entry(entry_id)
        verified = verified_payload is not None
        state = self.storage.load()
        # Find pending again
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
            )

        logger.info("Posted and verified entry_id=%s", entry_id)
        return CycleResult(posted=True, contribution=contribution)
