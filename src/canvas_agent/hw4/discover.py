"""Dynamically score and select a peer service provider (never hard-coded)."""

from __future__ import annotations

from canvas_agent.hw4.offer import SERVICE_TITLE
from canvas_agent.hw4.sanitize_peer import neutralize_injection
from canvas_agent.models import DiscussionSnapshot, ProviderCandidate

PREFERRED_KEYWORDS = (
    ("test", 3.0),
    ("qa", 3.0),
    ("quality", 2.0),
    ("debug", 2.5),
    ("review", 2.5),
    ("code review", 3.5),
    ("analys", 2.0),
    ("validat", 2.5),
    ("verif", 2.5),
    ("research", 2.0),
    ("source", 1.5),
    ("reliab", 3.0),
    ("audit", 3.0),
    ("red-team", 2.0),
    ("red team", 2.0),
    ("adversarial", 2.5),
    ("security", 2.0),
    ("fault", 1.5),
)

UNSUITABLE_KEYWORDS = (
    "meme",
    "joke only",
    "not a service",
    "ignore this",
)


def score_offer_text(text: str) -> tuple[float, str]:
    plain = neutralize_injection(text).casefold()
    if any(u in plain for u in UNSUITABLE_KEYWORDS) and "test" not in plain:
        return 0.0, "unsuitable_content"
    score = 0.0
    hits: list[str] = []
    for keyword, weight in PREFERRED_KEYWORDS:
        if keyword in plain:
            score += weight
            hits.append(keyword)
    if "service" in plain or "offer" in plain:
        score += 1.0
        hits.append("service/offer")
    reason = "keywords:" + ",".join(hits[:8]) if hits else "no_preferred_keywords"
    return score, reason


def list_candidate_providers(
    snapshot: DiscussionSnapshot,
    *,
    agent_user_id: int | None,
    rejected_ids: list[int],
    min_score: float = 2.0,
) -> list[ProviderCandidate]:
    candidates: list[ProviderCandidate] = []
    for entry in snapshot.entries:
        if entry.parent_id is not None:
            continue
        if agent_user_id is not None and entry.user_id == agent_user_id:
            continue
        if entry.id in rejected_ids:
            continue
        text = entry.message_text or ""
        if SERVICE_TITLE.casefold() in text.casefold() and agent_user_id == entry.user_id:
            continue
        score, reason = score_offer_text(text)
        if score < min_score:
            continue
        candidates.append(
            ProviderCandidate(
                entry_id=entry.id,
                user_id=entry.user_id,
                score=score,
                reason=reason,
                title_snippet=text.strip().splitlines()[0][:120] if text.strip() else "",
            )
        )
    candidates.sort(key=lambda c: (-c.score, c.entry_id))
    return candidates


def select_provider(
    candidates: list[ProviderCandidate],
) -> ProviderCandidate | None:
    if not candidates:
        return None
    # Dynamic: highest score; tie-break by entry_id already applied
    return candidates[0]
