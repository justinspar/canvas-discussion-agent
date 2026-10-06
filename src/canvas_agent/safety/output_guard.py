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
# Credentials / tokens / password-looking material
_SECRETISH_RE = re.compile(
    r"("
    r"api[_-]?key|access[_-]?token|canvas_token|authorization\s*:\s*bearer|"
    r"bearer\s+[a-z0-9\-._~+/]+=*|"
    r"sk-[a-z0-9]{10,}|sk-parley-|"
    r"password\s*[:=]|passwd\s*[:=]|secret\s*[:=]"
    r")",
    re.IGNORECASE,
)
# Grades / student records / personal identifiers that must not be posted
_SENSITIVE_RECORD_RE = re.compile(
    r"("
    r"\b(ssn|social\s+security)\b|"
    r"\b(ferpa)\b|"
    r"\bstudent\s+(id|record|records|grade|grades)\b|"
    r"\b(final|midterm|quiz|assignment)\s+grade\b|"
    r"\bgrade\s*[:=]\s*[A-F][+-]?\b|"
    r"\b\d{3}-\d{2}-\d{4}\b|"  # SSN-like
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"  # email addresses
    r")",
    re.IGNORECASE,
)

_BANNED_SNIPPETS = (
    "ignore previous instructions",
    "reveal the token",
    "canvas_token",
    "system prompt",
    "student record",
    "student records",
    "final grade",
    "private message",
    "confidential project",
    "my password",
    "api key is",
    "access token is",
    "delete this post",
    "edit their post",
    "overwrite their",
)


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
    if _SECRETISH_RE.search(message):
        raise OutputGuardError("message must not contain credentials or tokens")
    if _SENSITIVE_RECORD_RE.search(message):
        raise OutputGuardError(
            "message must not contain grades, student records, or personal data"
        )

    lowered = message.casefold()
    if any(s in lowered for s in _BANNED_SNIPPETS):
        raise OutputGuardError("message contains forbidden content")

    return AdvisorDecision(
        action="post",
        kind=decision.kind,
        parent_id=decision.parent_id if decision.kind is WriteKind.REPLY else None,
        message=message,
        rationale=decision.rationale,
    )
