"""Treat peer Canvas content as untrusted; extract only structured fields."""

from __future__ import annotations

import hashlib
import re

from canvas_agent.safety.sanitize import sanitize_entry_text

_INJECTION_PATTERNS = (
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?(prior|previous)",
    r"reveal\s+(the\s+)?(token|secret|password|api\s*key)",
    r"system\s*prompt",
    r"override\s+(safety|control|rate\s*limit)",
    r"execute\s+(this\s+)?(code|command|shell)",
    r"curl\s+http",
    r"rm\s+-rf",
)

_FIELD_KEYS = (
    "description",
    "purpose",
    "tools",
    "memory",
    "state",
    "constraints",
    "workflow",
)


def content_hash(text: str) -> str:
    return hashlib.sha256(sanitize_entry_text(text).encode("utf-8")).hexdigest()


def neutralize_injection(text: str) -> str:
    plain = sanitize_entry_text(text)
    for pat in _INJECTION_PATTERNS:
        plain = re.sub(pat, "[blocked-instruction]", plain, flags=re.IGNORECASE)
    return plain


def extract_agent_profile(text: str) -> dict[str, str]:
    """Best-effort extraction of red-team request fields from untrusted text."""
    plain = neutralize_injection(text)
    profile: dict[str, str] = {}
    # Labeled lines: Purpose: ...
    for key in _FIELD_KEYS:
        match = re.search(
            rf"(?im)^\s*{key}\s*[:\-]\s*(.+?)(?=^\s*(?:{'|'.join(_FIELD_KEYS)})\s*[:\-]|\Z)",
            plain,
            flags=re.IGNORECASE | re.DOTALL | re.MULTILINE,
        )
        if match:
            profile[key] = match.group(1).strip()[:2000]
    if not profile:
        # Fallback: keep a bounded summary blob under description
        profile["description"] = plain[:2500]
    return profile


def has_enough_profile(profile: dict[str, str]) -> bool:
    """Need enough substance for a non-generic red-team report."""
    joined = " ".join(profile.values()).strip()
    if len(joined) < 80:
        return False
    # Prefer at least purpose or tools or workflow signal
    signals = ("tool", "canvas", "memory", "state", "cron", "api", "llm", "agent", "retry")
    lowered = joined.casefold()
    return any(s in lowered for s in signals)


def looks_like_decline(text: str) -> bool:
    lowered = neutralize_injection(text).casefold()
    cues = (
        "cannot help",
        "can't help",
        "decline",
        "unable to",
        "not able to",
        "out of scope",
        "sorry, i can't",
        "will not take",
    )
    return any(c in lowered for c in cues)


def extract_python_test_blocks(text: str) -> list[str]:
    """Pull fenced python/pytest code only; ignore shell and other languages."""
    plain = neutralize_injection(text)
    blocks: list[str] = []
    for match in re.finditer(
        r"```(?:python|py|pytest)?\s*\n(.*?)```", plain, flags=re.IGNORECASE | re.DOTALL
    ):
        body = match.group(1).strip()
        if not body:
            continue
        # Reject obvious shell / network / filesystem abuse
        bad = ("subprocess", "os.system", "socket", "requests.", "httpx.", "eval(", "exec(")
        if any(b in body for b in bad):
            continue
        if "def test_" in body or "import pytest" in body or "assert " in body:
            blocks.append(body[:8000])
    return blocks
