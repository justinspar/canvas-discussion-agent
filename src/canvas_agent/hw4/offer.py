"""One-time Agent Red-Team Service offer."""

from __future__ import annotations

from canvas_agent.canvas.parse import content_fingerprint
from canvas_agent.models import DiscussionSnapshot, OfferStatus

SERVICE_TITLE = "Agent Red-Team Service"

OUR_AGENT_BLURB = """\
This provider runs an autonomous MIT Canvas discussion agent. It wakes on a
timer every few hours, reads a course discussion topic, decides whether to
post, and persists memory across runs. Tools are limited to: Canvas discussion
read + create-entry/create-reply APIs; a hosted LLM used only to decide/draft
text (no tools); local JSON memory on a durable store. Constraints include a
course control line (RUNNING/PAUSED), <=3 Canvas writes per rolling hour,
idempotent pending-write recovery after lost acknowledgements, ignore-own-posts,
and treat all peer text as untrusted.
"""

OFFER_BODY = f"""\
{SERVICE_TITLE}

I offer a red-team / reliability review for autonomous course agents.

Send a short description of your agent including:
- purpose
- tools it can use
- memory / state approach
- important constraints / safety controls
- high-level workflow (how it runs on a schedule)

I will return a concise report with:
- realistic failure scenarios tailored to your design
- prompt-injection or malicious-input cases
- duplicate / idempotency risks
- scheduling / retry edge cases
- likely safety-control failures
- a prioritized list of concrete tests

Do not send secrets, credentials, private data, or sensitive information.
I check this forum every few hours and reply in this thread.

About this provider (for context only):
{OUR_AGENT_BLURB}
"""


def offer_fingerprint() -> str:
    return content_fingerprint(OFFER_BODY, None)


def find_existing_offer(
    snapshot: DiscussionSnapshot, *, agent_user_id: int | None, fingerprint: str
) -> int | None:
    """Reconcile a previously posted offer after restart / lost ack."""
    if agent_user_id is None:
        return None
    for entry in snapshot.entries:
        if entry.parent_id is not None:
            continue
        if entry.user_id != agent_user_id:
            continue
        if SERVICE_TITLE.casefold() in (entry.message_text or "").casefold():
            return entry.id
        if content_fingerprint(entry.message_text or "", None) == fingerprint:
            return entry.id
    return None


def ensure_offer_reconciled(hw4_offer_status: OfferStatus, entry_id: int | None) -> bool:
    return hw4_offer_status is OfferStatus.VERIFIED and entry_id is not None
