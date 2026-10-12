"""HW4 phase machine: decide the single next write (or idle)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from canvas_agent.canvas.parse import content_fingerprint
from canvas_agent.hw4 import delegate, discover, offer, serve, use, verify
from canvas_agent.hw4.llm_helpers import draft_red_team_report
from canvas_agent.hw4.sanitize_peer import (
    extract_agent_profile,
    has_enough_profile,
    looks_like_decline,
)
from canvas_agent.models import (
    AcceptedWorkRecord,
    AgentState,
    DelegationStatus,
    DiscussionSnapshot,
    IncomingRequestRecord,
    IncomingRequestStatus,
    OfferStatus,
    ProviderCandidate,
    TipRecord,
    VerificationRecord,
    WriteKind,
)

logger = logging.getLogger(__name__)


@dataclass
class Hw4PlannedWrite:
    phase: str
    kind: WriteKind
    parent_id: int | None
    message: str
    rationale: str
    action_id: str
    meta: dict[str, Any]


@dataclass
class Hw4Idle:
    phase: str
    rationale: str
    verification_outcome: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _reconcile_offer(state: AgentState, snapshot: DiscussionSnapshot) -> None:
    hw4 = state.hw4
    fp = offer.offer_fingerprint()
    hw4.offer_fingerprint = fp
    existing = offer.find_existing_offer(
        snapshot, agent_user_id=state.agent_user_id, fingerprint=fp
    )
    if existing is not None:
        hw4.offer_entry_id = existing
        hw4.offer_status = OfferStatus.VERIFIED
        hw4.offer_verified = True


def _reject_provider(hw4: Any, *, reason: str) -> None:
    if hw4.selected_provider_entry_id is not None:
        if hw4.selected_provider_entry_id not in hw4.rejected_provider_entry_ids:
            hw4.rejected_provider_entry_ids.append(hw4.selected_provider_entry_id)
    hw4.selected_provider_entry_id = None
    hw4.selected_provider_user_id = None
    hw4.request_reply_id = None
    hw4.request_hash = None
    hw4.delegated_request_id = None
    hw4.task_description = None
    hw4.acceptance_criteria = None
    hw4.request_deadline = None
    hw4.correction_reply_id = None
    hw4.correction_request_id = None
    hw4.delegation_status = DelegationStatus.PROVIDER_DECLINED
    hw4.provider_rediscoveries += 1
    logger.info("Rejected unsuitable provider: %s", reason)


def _recover_unsuitable_selection(
    hw4: Any, snapshot: DiscussionSnapshot
) -> bool:
    """
    If the currently selected provider fails suitability, reject and clear
    awaiting request fields (when no accepted work yet). Returns True if rejected.
    """
    if hw4.selected_provider_entry_id is None:
        return False
    if hw4.accepted_work is not None or hw4.acknowledgment_id is not None:
        return False
    if hw4.delegation_status is DelegationStatus.ACCEPTED:
        return False

    offer_text = discover.provider_offer_text(
        snapshot, hw4.selected_provider_entry_id
    )
    if not offer_text:
        # Keep waiting if snapshot temporarily lacks the post; only reject when
        # we can read an unsuitable offer.
        return False
    if discover.is_suitable_provider(offer_text):
        return False

    _reject_provider(hw4, reason="unsuitable_offer")
    return True


def next_action(
    state: AgentState,
    snapshot: DiscussionSnapshot,
    *,
    llm_client: Any | None = None,
    llm_model: str | None = None,
    src_root: Path | None = None,
    repo_root: Path | None = None,
) -> Hw4PlannedWrite | Hw4Idle:
    """Pick the highest-priority HW4 action for this cycle."""
    _reconcile_offer(state, snapshot)
    hw4 = state.hw4

    # 1) Offer service once
    if hw4.offer_status is not OfferStatus.VERIFIED:
        return Hw4PlannedWrite(
            phase="offer_service",
            kind=WriteKind.ENTRY,
            parent_id=None,
            message=offer.OFFER_BODY,
            rationale="post_red_team_service_offer",
            action_id="offer:" + (hw4.offer_fingerprint or offer.offer_fingerprint()),
            meta={"type": "offer"},
        )

    # 2) Serve one incoming request
    incoming = serve.next_incoming_request(
        snapshot, hw4, agent_user_id=state.agent_user_id
    )
    if incoming is not None:
        rec = serve.register_seen(hw4, incoming)
        profile = extract_agent_profile(incoming.message_text or "")
        llm_report = None
        if has_enough_profile(profile) and llm_client is not None:
            llm_report = draft_red_team_report(
                profile, client=llm_client, model=llm_model
            )
        message, mode, _profile = serve.prepare_response_for_request(
            incoming, llm_report=llm_report
        )
        return Hw4PlannedWrite(
            phase="serve_incoming",
            kind=WriteKind.REPLY,
            parent_id=hw4.offer_entry_id,
            message=message,
            rationale=f"serve_{mode}_for_{incoming.id}",
            action_id=f"serve:{mode}:{incoming.id}:{rec.content_hash[:16]}",
            meta={
                "type": "serve",
                "mode": mode,
                "request_entry_id": incoming.id,
                "content_hash": rec.content_hash,
            },
        )

    # 3) One-time clarification under our own offer only if the live offer is
    # still the old wall-of-text format (Canvas posts cannot be edited).
    if hw4.offer_clarification_id is None and hw4.offer_entry_id is not None:
        clar_fp = offer.clarification_fingerprint(hw4.offer_entry_id)
        live_offer = next(
            (e for e in snapshot.entries if e.id == hw4.offer_entry_id), None
        )
        live_text = (live_offer.message_text if live_offer else "") or ""
        already_clear = (
            "**What I need from you**" in live_text
            and "SERVICE OFFER:" in live_text
        )
        for entry in snapshot.entries:
            if (
                entry.parent_id == hw4.offer_entry_id
                and state.agent_user_id is not None
                and entry.user_id == state.agent_user_id
                and "Clarifying my service offer" in (entry.message_text or "")
            ):
                hw4.offer_clarification_id = entry.id
                break
        if already_clear and hw4.offer_clarification_id is None:
            # Mark satisfied without posting a redundant self-reply.
            hw4.offer_clarification_id = hw4.offer_entry_id
        elif hw4.offer_clarification_id is None:
            return Hw4PlannedWrite(
                phase="offer_clarification",
                kind=WriteKind.REPLY,
                parent_id=hw4.offer_entry_id,
                message=offer.CLARIFICATION_BODY,
                rationale="clarify_own_offer_format",
                action_id=f"offer_clarification:{clar_fp[:16]}",
                meta={"type": "offer_clarification", "fingerprint": clar_fp},
            )

    # Recover from a previously selected unsuitable provider (e.g. clinic false positive)
    _recover_unsuitable_selection(hw4, snapshot)

    # Need rediscovery after decline/expiry/reject
    needs_new_provider = hw4.delegation_status in {
        DelegationStatus.NONE,
        DelegationStatus.PROVIDER_DECLINED,
        DelegationStatus.EXPIRED,
        DelegationStatus.REJECTED,
    } and hw4.request_reply_id is None

    if needs_new_provider:
        if hw4.provider_rediscoveries > 1 and hw4.delegation_status != DelegationStatus.NONE:
            return Hw4Idle(
                phase="delegation_exhausted",
                rationale="no_more_provider_retries",
            )
        # Always refresh candidates so LLM/deterministic drafting sees current offers.
        candidates = discover.list_candidate_providers(
            snapshot,
            agent_user_id=state.agent_user_id,
            rejected_ids=list(hw4.rejected_provider_entry_ids),
        )
        hw4.candidate_providers = candidates

        if (
            hw4.selected_provider_entry_id is None
            or hw4.delegation_status
            in {
                DelegationStatus.PROVIDER_DECLINED,
                DelegationStatus.EXPIRED,
                DelegationStatus.REJECTED,
            }
        ):
            if llm_client is None or not llm_model:
                logger.warning(
                    "HW4 provider selection without Parley LLM; using keyword fallback"
                )
            chosen = discover.select_provider(
                candidates,
                llm_client=llm_client,
                llm_model=llm_model,
            )
            if chosen is None:
                return Hw4Idle(phase="discover_provider", rationale="no_suitable_provider")
            # Exchange auditors require a draft service request to a worker peer.
            offer_preview = discover.provider_offer_text(snapshot, chosen.entry_id)
            if delegate.classify_capability(offer_preview) == "exchange_audit":
                worker = delegate.pick_worker_for_draft(
                    candidates, exclude_entry_id=chosen.entry_id
                )
                if worker is None:
                    for alt in candidates:
                        if alt.entry_id == chosen.entry_id:
                            continue
                        alt_text = discover.provider_offer_text(snapshot, alt.entry_id)
                        if delegate.classify_capability(alt_text) not in {
                            None,
                            "exchange_audit",
                        }:
                            chosen = alt
                            break
                    else:
                        return Hw4Idle(
                            phase="discover_provider",
                            rationale="exchange_auditor_needs_draft_request",
                        )
            hw4.selected_provider_entry_id = chosen.entry_id
            hw4.selected_provider_user_id = chosen.user_id
            if hw4.delegation_status != DelegationStatus.NONE:
                hw4.delegation_status = DelegationStatus.NONE

        if hw4.selected_provider_entry_id is not None:
            cand = next(
                (
                    c
                    for c in hw4.candidate_providers
                    if c.entry_id == hw4.selected_provider_entry_id
                ),
                None,
            )
            offer_text = discover.provider_offer_text(
                snapshot, hw4.selected_provider_entry_id
            )
            if cand is None:
                cand = ProviderCandidate(
                    entry_id=hw4.selected_provider_entry_id,
                    user_id=hw4.selected_provider_user_id,
                    score=1.0,
                    reason="selected",
                    offer_excerpt=offer_text[:800],
                    title_snippet=(offer_text.strip().splitlines() or [""])[0][:160],
                )
            built = delegate.build_request_message(
                cand,
                offer_text=offer_text,
                peer_candidates=list(hw4.candidate_providers),
                llm_client=llm_client,
                llm_model=llm_model,
            )
            if built is None:
                _reject_provider(hw4, reason="capability_mismatch")
                return Hw4Idle(
                    phase="discover_provider",
                    rationale="provider_capability_mismatch",
                )
            message, task, criteria, deadline = built
            fp = content_fingerprint(message, cand.entry_id)
            return Hw4PlannedWrite(
                phase="delegate_task",
                kind=WriteKind.REPLY,
                parent_id=cand.entry_id,
                message=message,
                rationale="delegate_task_to_provider",
                action_id=f"delegate:{cand.entry_id}:{fp[:16]}",
                meta={
                    "type": "delegate",
                    "request_hash": fp,
                    "deadline": deadline,
                    "task_description": task,
                    "acceptance_criteria": criteria,
                    "provider_entry_id": cand.entry_id,
                },
            )

    # Await / verify / correct / ack
    if hw4.request_reply_id is not None and hw4.acknowledgment_id is None:
        # Mid-await suitability check (recover bad live delegation)
        if _recover_unsuitable_selection(hw4, snapshot):
            return Hw4Idle(
                phase="await_result",
                rationale="rejected_unsuitable_provider",
            )

        provider_id = hw4.selected_provider_entry_id
        results = [
            e
            for e in snapshot.entries
            if e.parent_id == provider_id
            and e.id != hw4.request_reply_id
            and e.id not in hw4.provider_results_seen
            and (state.agent_user_id is None or e.user_id != state.agent_user_id)
            and e.id != hw4.correction_reply_id
            and e.id > (hw4.request_reply_id or 0)
        ]
        results.sort(key=lambda e: e.id)

        if not results:
            if (
                hw4.request_deadline
                and _utcnow() > hw4.request_deadline
                and hw4.delegation_status
                not in {DelegationStatus.ACCEPTED, DelegationStatus.EXPIRED}
            ):
                hw4.delegation_status = DelegationStatus.EXPIRED
                if hw4.selected_provider_entry_id:
                    hw4.rejected_provider_entry_ids.append(
                        hw4.selected_provider_entry_id
                    )
                hw4.selected_provider_entry_id = None
                hw4.request_reply_id = None
                hw4.request_hash = None
                hw4.delegated_request_id = None
                hw4.provider_rediscoveries += 1
                return Hw4Idle(phase="await_result", rationale="deadline_missed")
            return Hw4Idle(phase="await_result", rationale="waiting_for_provider")

        result = results[0]
        hw4.provider_results_seen.append(result.id)

        if looks_like_decline(result.message_text or ""):
            if hw4.selected_provider_entry_id:
                hw4.rejected_provider_entry_ids.append(hw4.selected_provider_entry_id)
            hw4.selected_provider_entry_id = None
            hw4.request_reply_id = None
            hw4.delegated_request_id = None
            hw4.request_hash = None
            hw4.delegation_status = DelegationStatus.PROVIDER_DECLINED
            hw4.provider_rediscoveries += 1
            return Hw4Idle(phase="await_result", rationale="provider_declined")

        outcome = verify.verify_provider_result(
            result.message_text or "", src_root=src_root
        )
        hw4.verification_results.append(
            VerificationRecord(
                result_entry_id=result.id,
                method=outcome.method,
                outcome=outcome.outcome,
                accepted=outcome.accepted,
                evidence=outcome.evidence[:1500],
                checked_at=_utcnow(),
            )
        )

        if outcome.accepted:
            path = use.apply_accepted_tests(outcome, repo_root=repo_root)
            hw4.accepted_work = AcceptedWorkRecord(
                result_entry_id=result.id,
                incorporated_path=path,
                reason=outcome.outcome,
                used_at=_utcnow(),
            )
            hw4.delegation_status = DelegationStatus.ACCEPTED
            tip_amt = use.tip_amount_for_outcome(outcome)
            msg = use.acknowledgment_message(
                accepted=True,
                tip_amount=tip_amt,
                useful_summary=outcome.method,
                request_id=hw4.delegated_request_id or "",
            )
            return Hw4PlannedWrite(
                phase="use_and_ack",
                kind=WriteKind.REPLY,
                parent_id=provider_id,
                message=msg,
                rationale="ack_accepted_work",
                action_id=f"ack:{result.id}",
                meta={
                    "type": "ack",
                    "result_entry_id": result.id,
                    "tip_amount": tip_amt,
                    "useful_summary": outcome.method,
                    "verification_outcome": outcome.outcome,
                },
            )

        if hw4.correction_reply_id is None:
            hw4.delegation_status = DelegationStatus.AWAITING_CORRECTION
            return Hw4PlannedWrite(
                phase="correction_request",
                kind=WriteKind.REPLY,
                parent_id=provider_id,
                message=use.correction_message(outcome),
                rationale="request_correction",
                action_id=f"correct:{result.id}:{uuid4().hex[:8]}",
                meta={
                    "type": "correction",
                    "result_entry_id": result.id,
                    "verification_outcome": outcome.outcome,
                },
            )
        hw4.delegation_status = DelegationStatus.REJECTED
        return Hw4Idle(
            phase="verify_result",
            rationale="verification_failed_after_correction",
            verification_outcome=outcome.outcome,
        )

    return Hw4Idle(phase="idle", rationale="no_hw4_write_needed")


def on_write_confirmed(
    state: AgentState,
    planned: Hw4PlannedWrite,
    *,
    canvas_entry_id: int,
) -> AgentState:
    """Update HW4 state after a verified Canvas write."""
    hw4 = state.hw4
    meta = planned.meta
    kind = meta.get("type")
    hw4.last_phase = planned.phase

    if kind == "offer":
        hw4.offer_entry_id = canvas_entry_id
        hw4.offer_status = OfferStatus.VERIFIED
        hw4.offer_verified = True
        hw4.offer_fingerprint = content_fingerprint(planned.message, None)
    elif kind == "other":
        # Agentic free-form write: track phase only
        pass
    elif kind == "offer_clarification":
        hw4.offer_clarification_id = canvas_entry_id
    elif kind == "serve":
        req_id = int(meta["request_entry_id"])
        rec = next(
            (r for r in hw4.incoming_requests if r.request_entry_id == req_id), None
        )
        if rec is None:
            rec = IncomingRequestRecord(
                request_entry_id=req_id,
                parent_offer_id=hw4.offer_entry_id or 0,
                content_hash=str(meta.get("content_hash") or ""),
            )
            hw4.incoming_requests.append(rec)
        if meta.get("mode") == "clarify":
            rec.status = IncomingRequestStatus.CLARIFY_SENT
            rec.clarification_entry_id = canvas_entry_id
        else:
            rec.status = IncomingRequestStatus.COMPLETED
            rec.response_entry_id = canvas_entry_id
    elif kind == "delegate":
        hw4.delegated_request_id = planned.action_id
        hw4.request_reply_id = canvas_entry_id
        hw4.request_hash = str(meta.get("request_hash") or "")
        hw4.task_description = str(meta.get("task_description") or "")
        hw4.acceptance_criteria = str(meta.get("acceptance_criteria") or "")
        deadline = meta.get("deadline")
        if isinstance(deadline, datetime):
            hw4.request_deadline = deadline
        hw4.delegation_status = DelegationStatus.AWAITING
        provider_entry = meta.get("provider_entry_id")
        if provider_entry is not None:
            hw4.selected_provider_entry_id = int(provider_entry)
    elif kind == "correction":
        hw4.correction_request_id = planned.action_id
        hw4.correction_reply_id = canvas_entry_id
        hw4.delegation_status = DelegationStatus.AWAITING_CORRECTION
    elif kind == "ack":
        hw4.acknowledgment_id = canvas_entry_id
        tip_amt = int(meta.get("tip_amount") or 0)
        if tip_amt > 0 and hw4.tip is None:
            hw4.tip = TipRecord(
                amount=tip_amt,
                reason=str(meta.get("useful_summary") or ""),
                reply_entry_id=canvas_entry_id,
                recorded_at=_utcnow(),
            )
        hw4.delegation_status = DelegationStatus.ACCEPTED

    state.hw4 = hw4
    return state
