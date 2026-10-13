"""Provider-specific service requests grounded in the selected offer text."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from canvas_agent.hw4.discover import capability_focus, is_suitable_provider
from canvas_agent.hw4.llm_helpers import OUR_NEEDS, reason_service_request
from canvas_agent.hw4.offer import SERVICE_TITLE
from canvas_agent.models import ProviderCandidate

DEFAULT_DEADLINE_HOURS = 48


def summarize_capability(offer_text: str, *, max_chars: int = 280) -> str:
    focus = capability_focus(offer_text)
    if not focus:
        return "(no offer text available)"
    lines = [ln.strip() for ln in focus.splitlines() if ln.strip()]
    head = lines[0] if lines else focus[:120]
    body = " ".join(lines[1:4]) if len(lines) > 1 else ""
    summary = f"{head} — {body}".strip(" —") if body else head
    return summary[:max_chars]


def classify_capability(offer_text: str) -> str | None:
    """Map provider offer to a task bucket we actually need, or None if mismatch."""
    if not is_suitable_provider(offer_text):
        return None
    focus = capability_focus(offer_text).casefold()
    if not focus:
        return None

    if any(
        k in focus
        for k in (
            "service offer, request, or returned result",
            "offer, request, or returned result",
            "proposed canvas-agent service",
            "before you rely on it",
            "accept, revise, or reject",
            "accept / revise / reject",
            "completeness and ambiguity",
            "planning and verification audit",
        )
    ) or (
        "audit" in focus
        and any(k in focus for k in ("offer", "request", "returned result", "design spec"))
        and any(k in focus for k in ("checklist", "accept", "revise", "reject", "self-contained"))
    ):
        return "exchange_audit"

    if any(
        k in focus
        for k in (
            "pre-post",
            "before your agent posts",
            "before you post",
            "draft",
        )
    ) and any(k in focus for k in ("safety", "check", "rules", "scan")):
        return "draft_safety"

    if any(
        k in focus
        for k in (
            "failure mode",
            "idempoten",
            "lost ack",
            "lost acknowledgement",
            "rate-limit failure",
            "reliability audit",
            "red-team",
            "red team",
        )
    ) or (
        "audit" in focus
        and any(
            k in focus
            for k in (
                "autonomous agent",
                "autonomous canvas agent",
                "agent design",
                "agent architecture",
                "workflow",
                "reliability",
                "for autonomous",
            )
        )
        and "offer, request" not in focus
        and "returned result" not in focus
    ):
        return "safety_audit"

    if any(
        k in focus
        for k in (
            "pytest",
            "adversarial",
            "edge-case",
            "edge case",
            "test design",
            "test generation",
            "unit test",
            "test suite",
        )
    ):
        return "test_design"

    if any(k in focus for k in ("code review", "debug")) and any(
        k in focus for k in ("agent", "canvas", "autonomous")
    ):
        return "code_review"

    if any(k in focus for k in ("research", "source check", "diligence", "public-source")):
        if any(k in focus for k in ("agent", "canvas", "autonomous", "safety", "api")):
            return "research"
        return None

    if any(k in focus for k in ("qa", "testing")) and any(
        k in focus for k in ("agent", "canvas", "autonomous")
    ):
        return "test_design"

    return None


def _excerpt(text: str, *, max_chars: int = 900) -> str:
    cleaned = re.sub(r"\n{3,}", "\n\n", text.strip())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 20].rstrip() + "\n…[truncated]"


def _direct_task(capability: str) -> dict[str, str]:
    if capability == "draft_safety":
        draft = (
            f"Draft reply under a peer offer:\n"
            f"Requesting a short reliability note on {SERVICE_TITLE} inputs "
            f"(purpose/tools/memory/constraints). No secrets."
        )
        return {
            "task": (
                "Please run your pre-post safety check on this agent draft before we would post it:\n\n"
                f"--- BEGIN DRAFT ---\n{draft}\n--- END DRAFT ---"
            ),
            "criteria": (
                "Acceptance: a structured safety report covering your advertised "
                "checks, with a clear pass/fail or equivalent. No secrets."
            ),
        }
    if capability == "safety_audit":
        return {
            "task": (
                "Audit our autonomous Canvas agent for control-line, lost-ack idempotency, "
                "and rate-limit failure modes. Focus on: (1) PAUSED before write, "
                "(2) POST succeeded but ack lost, (3) >3 posts/hour under retry pressure."
            ),
            "criteria": (
                "Acceptance: at least 3 concrete failure scenarios with reproduction steps "
                "and one prioritized mitigation each. No secrets. Independent verification "
                "will check scenarios against our safety modules."
            ),
        }
    if capability == "test_design":
        return {
            "task": (
                "Design pytest-style adversarial / edge-case tests for our Canvas HTML "
                "parser, content fingerprinting, and lost-ack / pending-write recovery. "
                "Prefer concrete assertable cases over prose."
            ),
            "criteria": (
                "Acceptance: at least 3 test cases with inputs + expected asserts. "
                "No secrets. We will independently run or map them to our test suite."
            ),
        }
    if capability == "code_review":
        return {
            "task": (
                "Review our Canvas write path for duplicate posts under lost acknowledgements "
                "and rate-limit races. Identify concrete bugs or missing guards."
            ),
            "criteria": (
                "Acceptance: at least 2 concrete findings with file/function references "
                "or clear behavioral descriptions. No secrets."
            ),
        }
    # research
    return {
        "task": (
            "Research short, source-backed notes on Canvas discussion API create-entry "
            "idempotency and rate-limit pitfalls relevant to autonomous agents "
            "(public docs only)."
        ),
        "criteria": (
            "Acceptance: 3 findings with public sources. No secrets. "
            "We will spot-check sources independently."
        ),
    }


def build_draft_service_request(
    *,
    worker_offer_text: str,
    worker_entry_id: int | None = None,
) -> str | None:
    """
    Prerequisite payload for exchange auditors: a complete draft service request
    we intend to send to a *worker* provider (not the auditor).
    """
    cap = classify_capability(worker_offer_text)
    if cap is None or cap == "exchange_audit":
        return None
    direct = _direct_task(cap)
    target = summarize_capability(worker_offer_text)
    dest = f"provider entry_id={worker_entry_id}" if worker_entry_id else "a suitable worker provider"
    return (
        f"DRAFT service request (not yet posted) to {dest}\n"
        f"Target offer summary: {target}\n\n"
        f"Inputs / task:\n{direct['task']}\n\n"
        f"Result I want + how I will check it:\n{direct['criteria']}\n\n"
        "Notes: public/synthetic class data only; no secrets or credentials."
    )


def pick_worker_for_draft(
    peer_candidates: list[ProviderCandidate],
    *,
    exclude_entry_id: int | None,
) -> ProviderCandidate | None:
    for cand in peer_candidates:
        if exclude_entry_id is not None and cand.entry_id == exclude_entry_id:
            continue
        text = cand.offer_excerpt or cand.title_snippet
        cap = classify_capability(text)
        if cap and cap != "exchange_audit":
            return cand
    return None


def _exchange_audit_task(draft_request: str) -> dict[str, str]:
    payload = _excerpt(draft_request, max_chars=1200)
    return {
        "task": (
            "Please audit the following DRAFT service request before we post it to "
            "another provider. This draft is the required input for your exchange/"
            "planning audit (public/synthetic class content only).\n\n"
            f"--- BEGIN DRAFT SERVICE REQUEST ---\n{payload}\n"
            "--- END DRAFT SERVICE REQUEST ---\n\n"
            "What we plan to do with your result: if ACCEPT, post a finalized request "
            "to the target provider; if REVISE, incorporate your notes first; if REJECT, "
            "choose a different provider/task."
        ),
        "criteria": (
            "Acceptance: reply with (1) concrete missing/ambiguous items if any, "
            "(2) safety guidance (credentials / untrusted peer text / injection), "
            "(3) verification suggestions we can run locally, and "
            "(4) a final recommendation ACCEPT, REVISE, or REJECT. "
            "No secrets. We will check that those four elements are present."
        ),
    }


def choose_task_for_provider(
    candidate: ProviderCandidate,
    *,
    offer_text: str | None = None,
    peer_candidates: list[ProviderCandidate] | None = None,
    llm_client: Any | None = None,
    llm_model: str | None = None,
) -> dict[str, str] | None:
    """Build a task inside the provider's advertised capability, or None if unsuitable."""
    text = offer_text if offer_text is not None else (candidate.offer_excerpt or "")
    if not text.strip():
        text = candidate.title_snippet or candidate.reason

    peers = peer_candidates or []
    worker = pick_worker_for_draft(peers, exclude_entry_id=candidate.entry_id)
    draft_request = None
    if worker is not None:
        draft_request = build_draft_service_request(
            worker_offer_text=worker.offer_excerpt or worker.title_snippet,
            worker_entry_id=worker.entry_id,
        )

    # Prefer LLM reasoning when available.
    llm = reason_service_request(
        provider_offer=text,
        draft_service_request=draft_request,
        our_needs=OUR_NEEDS,
        client=llm_client,
        model=llm_model,
    )
    if llm is not None:
        if not llm.get("suitable"):
            return None
        return {"task": str(llm["task"]), "criteria": str(llm["criteria"])}

    # Deterministic fallback
    capability = classify_capability(text)
    if capability is None:
        return None
    if capability == "exchange_audit":
        if not draft_request:
            # Prerequisite missing: cannot honestly hire an exchange auditor yet.
            return None
        return _exchange_audit_task(draft_request)
    return _direct_task(capability)


def build_request_message(
    candidate: ProviderCandidate,
    *,
    offer_text: str | None = None,
    peer_candidates: list[ProviderCandidate] | None = None,
    llm_client: Any | None = None,
    llm_model: str | None = None,
    now: datetime | None = None,
) -> tuple[str, str, str, datetime] | None:
    """
    Returns (message, task, criteria, deadline) or None if provider unsuitable.
    """
    text = offer_text if offer_text is not None else (candidate.offer_excerpt or "")
    chosen = choose_task_for_provider(
        candidate,
        offer_text=text,
        peer_candidates=peer_candidates,
        llm_client=llm_client,
        llm_model=llm_model,
    )
    if chosen is None:
        return None

    now = now or datetime.now(timezone.utc)
    deadline = now + timedelta(hours=DEFAULT_DEADLINE_HOURS)
    request_id = str(uuid4())
    capability_summary = summarize_capability(text or candidate.title_snippet)

    message = (
        f"Service request (request_id={request_id})\n\n"
        f"You offered: {capability_summary}\n\n"
        f"Please perform work inside that advertised capability.\n\n"
        f"Inputs / task:\n{chosen['task']}\n\n"
        f"Result I want + how I will check it:\n{chosen['criteria']}\n\n"
        f"Deadline (UTC): {deadline.isoformat()}\n\n"
        "Reply in this same offer thread with the deliverable. "
        "No separate acceptance negotiation is required — I will check and use "
        "the result on my next run. You may decline if you cannot do the task. "
        "Do not include secrets or credentials."
    )
    return message, chosen["task"], chosen["criteria"], deadline
