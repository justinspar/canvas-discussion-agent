"""Validate LLM draft text before any Canvas write."""

from __future__ import annotations

import re

from canvas_agent.canvas.parse import html_to_text
from canvas_agent.models import AdvisorDecision, WriteKind

MAX_MESSAGE_LEN = 4000
_CONTROL_LINE_RE = re.compile(
    r"COURSE-TEAM\s+CONTROL\s*:",
    re.IGNORECASE,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


class OutputGuardError(ValueError):
    pass


def validate_decision(decision: AdvisorDecision) -> AdvisorDecision:
    if decision.action == "abstain":
        return AdvisorDecision(action="abstain", rationale=decision.rationale)

    if decision.action != "post":
        raise OutputGuardError("invalid action")

    if decision.kind not in {WriteKind.ENTRY, WriteKind.REPLY}:
        raise OutputGuardError("post requires kind entry|reply")

    if decision.kind is WriteKind.REPLY and decision.parent_id is None:
        raise OutputGuardError("reply requires parent_id")

    if decision.kind is WriteKind.ENTRY and decision.parent_id is not None:
        raise OutputGuardError("top-level entry must not set parent_id")

    message = (decision.message or "").strip()
    if not message:
        raise OutputGuardError("empty message")

    # Reject HTML / scripts; require plain text
    if _HTML_TAG_RE.search(message):
        message = html_to_text(message).strip()
    if not message:
        raise OutputGuardError("message empty after sanitization")
    if len(message) > MAX_MESSAGE_LEN:
        raise OutputGuardError("message too long")
    if _CONTROL_LINE_RE.search(message):
        raise OutputGuardError("message must not mimic control line")
    # Block obvious instruction-injection payloads in outbound text
    lowered = message.casefold()
    banned_snippets = (
        "ignore previous instructions",
        "reveal the token",
        "canvas_token",
        "system prompt",
    )
    if any(s in lowered for s in banned_snippets):
        raise OutputGuardError("message contains forbidden content")

    return AdvisorDecision(
        action="post",
        kind=decision.kind,
        parent_id=decision.parent_id if decision.kind is WriteKind.REPLY else None,
        message=message,
        rationale=decision.rationale,
    )
