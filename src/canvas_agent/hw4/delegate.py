"""Provider-specific service requests grounded in the selected offer text."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from canvas_agent.hw4.discover import capability_focus, is_suitable_provider
from canvas_agent.hw4.offer import OFFER_BODY, SERVICE_TITLE
from canvas_agent.hw4.sanitize_peer import neutralize_injection
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

    # Exchange / planning audit: they review offer/request/result *text*, not our internals.
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

    # Pre-post draft safety check
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

    # True agent-reliability / internals audit (must look like auditing the agent, not ops text)
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

    # Last resort: agent testing/QA wording in the focus section only
    if any(k in focus for k in ("qa", "testing")) and any(
        k in focus for k in ("agent", "canvas", "autonomous")
    ):
        return "test_design"

    return None


def _excerpt_for_audit(text: str, *, max_chars: int = 900) -> str:
    cleaned = re.sub(r"\n{3,}", "\n\n", text.strip())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 20].rstrip() + "\n…[truncated]"


def _task_for_capability(capability: str) -> dict[str, str]:
    if capability == "exchange_audit":
        payload = _excerpt_for_audit(OFFER_BODY)
        return {
            "task": (
                "Please audit the following Canvas-agent service offer text before we keep "
                "relying on it as our HW4 offer. Public/synthetic class content only.\n\n"
                f"--- BEGIN OFFER TO AUDIT ---\n{payload}\n--- END OFFER ---\n\n"
                "What we plan to do with your result: revise our offer wording and "
                "request-handling checklist if you recommend REVISE/REJECT; keep using it "
                "if you recommend ACCEPT."
            ),
            "criteria": (
                "Acceptance: reply with (1) concrete missing/ambiguous items if any, "
                "(2) safety guidance (credentials / untrusted peer text / injection), "
                "(3) verification suggestions we can run locally, and "
                "(4) a final recommendation ACCEPT, REVISE, or REJECT. "
                "No secrets. We will check that those four elements are present."
            ),
        }
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
                "Acceptance: a deterministic-style safety report covering your advertised "
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


def choose_task_for_provider(
    candidate: ProviderCandidate, *, offer_text: str | None = None
) -> dict[str, str] | None:
    """Build a task inside the provider's advertised capability, or None if unsuitable."""
    text = offer_text if offer_text is not None else (candidate.offer_excerpt or "")
    if not text.strip():
        text = candidate.title_snippet or candidate.reason
    capability = classify_capability(text)
    if capability is None:
        return None
    return _task_for_capability(capability)


def build_request_message(
    candidate: ProviderCandidate,
    *,
    offer_text: str | None = None,
    now: datetime | None = None,
) -> tuple[str, str, str, datetime] | None:
    """
    Returns (message, task, criteria, deadline) or None if provider unsuitable.
    """
    text = offer_text if offer_text is not None else (candidate.offer_excerpt or "")
    chosen = choose_task_for_provider(candidate, offer_text=text)
    if chosen is None:
        return None

    now = now or datetime.now(timezone.utc)
    deadline = now + timedelta(hours=DEFAULT_DEADLINE_HOURS)
    request_id = str(uuid4())
    capability_summary = summarize_capability(text or candidate.title_snippet)

    message = (
        f"Service request (request_id={request_id})\n\n"
        f"You offered: {capability_summary}\n\n"
        f"Please perform work inside that advertised capability "
        f"(not unrelated agent-internals work).\n\n"
        f"Inputs / task:\n{chosen['task']}\n\n"
        f"Result I want + how I will check it:\n{chosen['criteria']}\n\n"
        f"Deadline (UTC): {deadline.isoformat()}\n\n"
        "Reply in this same offer thread with the deliverable (free-form is fine). "
        "No separate acceptance negotiation is required — I will check and use "
        "the result on my next run. You may decline if you cannot do the task. "
        "Do not include secrets or credentials."
    )
    return message, chosen["task"], chosen["criteria"], deadline
