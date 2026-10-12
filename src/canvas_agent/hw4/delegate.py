"""Build a real delegated task for a selected peer service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from canvas_agent.canvas.parse import content_fingerprint
from canvas_agent.hw4.sanitize_peer import neutralize_injection
from canvas_agent.models import ProviderCandidate

DEFAULT_DEADLINE_HOURS = 36

TASK_TEMPLATE = """\
Request for your advertised service

Context: I operate an autonomous Canvas discussion agent with:
- a COURSE-TEAM CONTROL line gate (RUNNING/PAUSED) checked before writes
- pending-write idempotency for lost acknowledgements
- a rolling <=3 posts/hour rate limiter
- peer text treated as untrusted (prompt-injection risk)

Task: Please {task_focus}

Specific behavior under evaluation:
{behavior}

Please return:
{deliverable}

Acceptance criteria:
{acceptance}

How I will verify independently:
{verification}

Deadline: please reply in this thread within {deadline_hours} hours of this request
(UTC deadline approximately {deadline_iso}).

Do not ask me for API keys, Canvas tokens, or private repository secrets.
"""


def choose_task_for_provider(candidate: ProviderCandidate) -> dict[str, str]:
    reason = (candidate.reason + " " + candidate.title_snippet).casefold()
    if any(k in reason for k in ("test", "qa", "adversarial", "debug")):
        return {
            "task_focus": (
                "generate adversarial pytest-style tests for a Canvas control-line "
                "parser and lost-acknowledgement / duplicate-prevention behavior"
            ),
            "behavior": (
                "may_post() must allow only RUNNING; PAUSED/UNKNOWN must block. "
                "After an ambiguous POST, the agent must reconcile by fingerprint "
                "and must not create a second identical post."
            ),
            "deliverable": (
                "1-3 concise pytest tests (python fenced code only) that assert "
                "control-gate fail-closed behavior and/or duplicate prevention. "
                "No shell commands."
            ),
            "acceptance": (
                "Tests must be valid Python, target the described behaviors, and "
                "catch at least one realistic defect if the gate/idempotency logic "
                "were broken."
            ),
            "verification": (
                "I will run your tests against the real implementation and against "
                "a deliberately broken mutant; I accept only if they pass on the "
                "good code and fail on the mutant."
            ),
        }
    if any(k in reason for k in ("review", "audit", "analys", "reliab")):
        return {
            "task_focus": (
                "audit failure-recovery and rate-limiting design for an autonomous "
                "Canvas poster"
            ),
            "behavior": (
                "uncertain write acknowledgements, retries with backoff, and a "
                "course-wide 3 posts/hour ceiling"
            ),
            "deliverable": (
                "a short audit with concrete findings (severity-ordered) and "
                "specific checks I can run; no generic advice"
            ),
            "acceptance": (
                "Each finding must map to a real failure mode (lost ack, overlap, "
                "rate window, control-line) and include a falsifiable check"
            ),
            "verification": (
                "I will independently inspect my control/idempotency/rate-limit "
                "code paths and reject fabricated or irrelevant findings"
            ),
        }
    return {
        "task_focus": (
            "validate prompt-injection defenses for an agent that reads untrusted "
            "Canvas posts"
        ),
        "behavior": (
            "peer text must not override instructions, reveal secrets, or expand tools"
        ),
        "deliverable": (
            "a prioritized list of injection cases and concrete validation checks"
        ),
        "acceptance": (
            "Cases must be specific to forum-sourced untrusted input and include "
            "expected safe outcomes"
        ),
        "verification": (
            "I will cross-check each case against my sanitizer/output-guard rules "
            "and reject irrelevant items"
        ),
    }


def build_request_message(
    candidate: ProviderCandidate, *, now: datetime | None = None
) -> tuple[str, str, datetime, dict[str, str]]:
    now = now or datetime.now(timezone.utc)
    deadline = now + timedelta(hours=DEFAULT_DEADLINE_HOURS)
    task = choose_task_for_provider(candidate)
    message = TASK_TEMPLATE.format(
        deadline_hours=DEFAULT_DEADLINE_HOURS,
        deadline_iso=deadline.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        **task,
    )
    # Keep provider title out of fingerprint noise beyond parent id
    fp = content_fingerprint(message, candidate.entry_id)
    meta = {
        "task_description": neutralize_injection(task["task_focus"]),
        "acceptance_criteria": neutralize_injection(task["acceptance"]),
    }
    return message, fp, deadline, meta
