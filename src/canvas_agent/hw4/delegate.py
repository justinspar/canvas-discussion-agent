"""Provider-specific service requests grounded in the selected offer text."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from canvas_agent.hw4.discover import is_suitable_provider
from canvas_agent.hw4.sanitize_peer import neutralize_injection
from canvas_agent.models import ProviderCandidate

DEFAULT_DEADLINE_HOURS = 48


def summarize_capability(offer_text: str, *, max_chars: int = 280) -> str:
    plain = neutralize_injection(offer_text).strip()
    if not plain:
        return "(no offer text available)"
    # Prefer first non-empty line + a bit of body
    lines = [ln.strip() for ln in plain.splitlines() if ln.strip()]
    head = lines[0] if lines else plain[:120]
    body = " ".join(lines[1:4]) if len(lines) > 1 else ""
    summary = f"{head} — {body}".strip(" —") if body else head
    return summary[:max_chars]


def classify_capability(offer_text: str) -> str | None:
    """Map provider offer to a task bucket we actually need, or None if mismatch."""
    if not is_suitable_provider(offer_text):
        return None
    plain = neutralize_injection(offer_text).casefold()

    if any(
        k in plain
        for k in (
            "safety",
            "verification",
            "audit",
            "reliab",
            "control line",
            "idempoten",
            "rate limit",
            "lost ack",
            "prompt injection",
        )
    ):
        return "safety_audit"

    if any(
        k in plain
        for k in (
            "pytest",
            "adversarial",
            "edge-case",
            "edge case",
            "test design",
            "test generation",
            "unit test",
            "qa",
        )
    ):
        return "test_design"

    if any(k in plain for k in ("code review", "debug", "validat", "verif")) and any(
        k in plain for k in ("agent", "canvas", "autonomous")
    ):
        return "code_review"

    if "research" in plain or "source" in plain or "diligence" in plain:
        # Only if already passed agent suitability
        if any(k in plain for k in ("agent", "canvas", "autonomous", "safety")):
            return "research"
        return None

    if any(k in plain for k in ("test", "review")) and any(
        k in plain for k in ("agent", "canvas", "autonomous")
    ):
        return "test_design"

    return None


def _task_for_capability(capability: str) -> dict[str, str]:
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
        f"Please perform work inside that advertised capability.\n\n"
        f"Inputs / task:\n{chosen['task']}\n\n"
        f"Result I want + how I will check it:\n{chosen['criteria']}\n\n"
        f"Deadline (UTC): {deadline.isoformat()}\n\n"
        "Reply in this same offer thread with the deliverable (free-form is fine). "
        "No separate acceptance negotiation is required — I will check and use "
        "the result on my next run. You may decline if you cannot do the task. "
        "Do not include secrets or credentials."
    )
    return message, chosen["task"], chosen["criteria"], deadline
