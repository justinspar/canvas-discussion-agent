"""Treat peer Canvas content as untrusted; extract only structured fields."""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING

from canvas_agent.safety.sanitize import sanitize_entry_text

if TYPE_CHECKING:
    from canvas_agent.models import DiscussionEntry, DiscussionSnapshot, Hw4State

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


def neutralize_injection(text: str, *, max_chars: int | None = 4000) -> str:
    plain = sanitize_entry_text(text, max_chars=max_chars)
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


def looks_like_peer_hire_request(text: str) -> bool:
    """True if this looks like another peer hiring the same provider (not a deliverable)."""
    lowered = neutralize_injection(text).casefold()
    strong = (
        "i would like to use your",
        "i'd like to use your",
        "i want to use your",
        "want to use your service",
        "you offered:",
        "hiring your",
        "please take this request",
    )
    if any(s in lowered for s in strong):
        return True
    # Common HW4 request shape without being a report
    hire_bits = sum(
        1
        for s in (
            "how i will check",
            "how i will verify",
            "desired result",
            "acceptance criteria",
            "deadline:",
            "task:",
        )
        if s in lowered
    )
    deliverable_bits = sum(
        1
        for s in (
            "finding",
            "scope tier",
            "overall risk",
            "pass / partial",
            "concrete test",
            "red-team report",
            "audit report",
        )
        if s in lowered
    )
    return hire_bits >= 2 and deliverable_bits == 0


def is_plausible_provider_result(
    entry: DiscussionEntry,
    *,
    provider_user_id: int | None,
) -> bool:
    """Filter out other peers' hire posts under the same offer thread."""
    if provider_user_id is not None and entry.user_id != provider_user_id:
        return False
    if looks_like_peer_hire_request(entry.message_text or ""):
        return False
    return True


def pick_provider_result(
    snapshot: DiscussionSnapshot,
    hw4: Hw4State,
    *,
    agent_user_id: int | None,
) -> tuple[DiscussionEntry | None, list[int]]:
    """
    Choose the next plausible provider deliverable under the hired offer.

    Returns (result_or_none, noise_entry_ids). Noise ids should be marked seen
    without treating them as accepted work (other peers hiring the same provider).
    """
    provider_id = hw4.selected_provider_entry_id
    request_id = hw4.request_reply_id
    if provider_id is None or request_id is None:
        return None, []

    # Resolve provider author if missing from memory (older delegations).
    provider_user_id = hw4.selected_provider_user_id
    if provider_user_id is None:
        offer_entry = next((e for e in snapshot.entries if e.id == provider_id), None)
        if offer_entry is not None:
            provider_user_id = offer_entry.user_id

    noise: list[int] = []
    candidates = [
        e
        for e in snapshot.entries
        if e.parent_id == provider_id
        and e.id != request_id
        and e.id not in hw4.provider_results_seen
        and (agent_user_id is None or e.user_id != agent_user_id)
        and e.id != hw4.correction_reply_id
        and e.id > request_id
    ]
    candidates.sort(key=lambda e: e.id)
    for entry in candidates:
        if is_plausible_provider_result(entry, provider_user_id=provider_user_id):
            return entry, noise
        noise.append(entry.id)
    return None, noise


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
