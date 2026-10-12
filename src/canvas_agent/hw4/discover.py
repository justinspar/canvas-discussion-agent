"""Dynamically score and select a peer service provider (never hard-coded)."""

from __future__ import annotations

from canvas_agent.hw4.offer import LEGACY_SERVICE_TITLE, SERVICE_TITLE
from canvas_agent.hw4.sanitize_peer import neutralize_injection
from canvas_agent.models import DiscussionSnapshot, ProviderCandidate

SERVICE_FRAME_SIGNALS = (
    "service offer",
    "service offer:",
    "i offer",
    "we offer",
    "offering a",
    "advertised service",
    "**what i need",
    "what you get",
)

AGENT_RELEVANCE = (
    ("canvas", 3.0),
    ("agent", 2.5),
    ("autonomous", 2.5),
    ("control line", 4.0),
    ("idempoten", 3.5),
    ("rate limit", 3.0),
    ("prompt injection", 3.5),
    ("pytest", 3.0),
    ("reliab", 3.0),
    ("verification", 3.0),
    ("safety", 2.5),
    ("audit", 2.5),
    ("adversarial", 2.5),
    ("edge-case", 2.0),
    ("edge case", 2.0),
    ("lost ack", 3.5),
    ("acknowledgement", 2.0),
    ("discussion", 1.5),
)

PREFERRED_KEYWORDS = (
    ("test", 1.5),
    ("qa", 2.0),
    ("debug", 2.0),
    ("review", 1.5),
    ("code review", 3.0),
    ("validat", 2.0),
    ("verif", 2.0),
    ("research", 1.0),
    ("security", 2.0),
)

OFF_DOMAIN_PENALTIES = (
    ("clinic", 8.0),
    ("hospital", 8.0),
    ("battleship", 10.0),
    ("ghost fleet", 10.0),
    ("window into a real place", 10.0),
    ("opportunity diligence", 6.0),
    ("business idea", 5.0),
    ("fictional", 4.0),
    ("meme", 6.0),
    ("joke only", 8.0),
    ("co-op", 3.0),
    ("sonar", 4.0),
    ("robotics and ai concept", 3.0),
)

MIN_SCORE = 5.0


def has_service_frame(text: str) -> bool:
    plain = neutralize_injection(text).casefold()
    return any(s in plain for s in SERVICE_FRAME_SIGNALS)


def is_suitable_provider(text: str) -> bool:
    """True only for agent-relevant service offers (not narrative/clinic/games)."""
    score, reason, agent_hits = score_offer_text(text)
    if score < MIN_SCORE:
        return False
    if "off_domain" in reason or "no_service_frame" in reason:
        return False
    return agent_hits >= 1


def score_offer_text(text: str) -> tuple[float, str, int]:
    plain = neutralize_injection(text).casefold()
    if not has_service_frame(text):
        return 0.0, "no_service_frame", 0

    score = 1.0  # base for having a service frame
    hits: list[str] = ["service_frame"]
    agent_hits = 0

    for keyword, weight in AGENT_RELEVANCE:
        if keyword in plain:
            score += weight
            hits.append(keyword)
            agent_hits += 1

    for keyword, weight in PREFERRED_KEYWORDS:
        if keyword in plain:
            score += weight
            hits.append(keyword)

    for keyword, penalty in OFF_DOMAIN_PENALTIES:
        if keyword in plain:
            score -= penalty
            hits.append(f"-{keyword}")

    if agent_hits < 1:
        # Generic "test/review" without agent/Canvas relevance is not enough
        score = min(score, MIN_SCORE - 0.1)
        hits.append("no_agent_relevance")

    reason = "keywords:" + ",".join(hits[:12])
    if score < 0:
        reason = "off_domain:" + reason
    return score, reason, agent_hits


def list_candidate_providers(
    snapshot: DiscussionSnapshot,
    *,
    agent_user_id: int | None,
    rejected_ids: list[int],
    min_score: float = MIN_SCORE,
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
        # Never select our own red-team offer if somehow attributed differently
        if SERVICE_TITLE.casefold() in text.casefold():
            continue
        if LEGACY_SERVICE_TITLE.casefold() in text.casefold() and "red-team" in text.casefold():
            if agent_user_id is not None and entry.user_id == agent_user_id:
                continue
        score, reason, _agent_hits = score_offer_text(text)
        if score < min_score:
            continue
        if not is_suitable_provider(text):
            continue
        excerpt = neutralize_injection(text).strip()[:800]
        title = excerpt.splitlines()[0][:160] if excerpt else ""
        candidates.append(
            ProviderCandidate(
                entry_id=entry.id,
                user_id=entry.user_id,
                score=score,
                reason=reason,
                title_snippet=title,
                offer_excerpt=excerpt,
            )
        )
    candidates.sort(key=lambda c: (-c.score, c.entry_id))
    return candidates


def select_provider(
    candidates: list[ProviderCandidate],
) -> ProviderCandidate | None:
    if not candidates:
        return None
    return candidates[0]


def provider_offer_text(
    snapshot: DiscussionSnapshot, entry_id: int | None
) -> str:
    if entry_id is None:
        return ""
    for entry in snapshot.entries:
        if entry.id == entry_id and entry.parent_id is None:
            return entry.message_text or ""
    return ""
