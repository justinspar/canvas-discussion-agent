"""Sanitize untrusted Canvas discussion content before LLM use."""

from __future__ import annotations

from canvas_agent.canvas.parse import html_to_text, normalize_message
from canvas_agent.models import DiscussionEntry, DiscussionSnapshot


UNTRUSTED_START = "<<<UNTRUSTED_DISCUSSION>>>"
UNTRUSTED_END = "<<<END>>>"


def sanitize_entry_text(text: str) -> str:
    plain = html_to_text(text)
    # Neutralize delimiter spoofing
    plain = plain.replace(UNTRUSTED_START, "[untrusted-marker]")
    plain = plain.replace(UNTRUSTED_END, "[untrusted-marker]")
    # Cap individual message size for prompts
    if len(plain) > 4000:
        plain = plain[:4000] + "…"
    return plain


def format_discussion_for_llm(
    snapshot: DiscussionSnapshot,
    *,
    agent_user_id: int | None,
    exclude_own: bool = True,
) -> str:
    lines: list[str] = [UNTRUSTED_START]
    lines.append(f"topic_id={snapshot.topic_id}")
    for entry in snapshot.entries:
        if exclude_own and agent_user_id is not None and entry.user_id == agent_user_id:
            continue
        msg = sanitize_entry_text(entry.message_text)
        lines.append(
            f"[entry_id={entry.id} user_id={entry.user_id} parent_id={entry.parent_id}] {msg}"
        )
    lines.append(UNTRUSTED_END)
    return "\n".join(lines)


def entries_excluding_own(
    entries: list[DiscussionEntry], agent_user_id: int | None
) -> list[DiscussionEntry]:
    if agent_user_id is None:
        return list(entries)
    return [e for e in entries if e.user_id != agent_user_id]


def is_near_duplicate(a: str, b: str) -> bool:
    return normalize_message(a) == normalize_message(b)
