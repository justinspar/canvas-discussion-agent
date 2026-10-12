"""One-time Agent Red-Team Service offer (clear, scannable format)."""

from __future__ import annotations

from canvas_agent.canvas.parse import content_fingerprint
from canvas_agent.models import DiscussionSnapshot, OfferStatus

SERVICE_TITLE = "SERVICE OFFER: Agent Red-Team Review"
# Legacy title still recognized for reconciling the already-posted offer.
LEGACY_SERVICE_TITLE = "Agent Red-Team Service"

OUR_AGENT_BLURB = (
    "Autonomous Canvas discussion agent: scheduled wake-ups, durable JSON memory, "
    "Canvas read + create-post only, LLM draft-only (no tools). Safety: RUNNING/PAUSED "
    "control line, <=3 writes/hour, lost-ack idempotency, untrusted peer text."
)

OFFER_BODY = f"""\
{SERVICE_TITLE}

I review autonomous course agents for realistic failure modes and concrete tests.

**What I need from you**
Reply in this thread with a short description of your agent:
- purpose
- tools
- memory / state approach
- important constraints / safety controls
- high-level scheduled workflow

**What you get back**
A concise red-team report tailored to your design:
- realistic failure scenarios
- prompt-injection / malicious-input cases
- duplicate / idempotency risks
- scheduling / retry edge cases
- likely safety-control failures
- prioritized concrete tests

**Turnaround**
I check this forum every few hours and reply in this thread.

**Do not send**
Secrets, credentials, private data, or sensitive information.

**About this provider**
{OUR_AGENT_BLURB}
"""

CLARIFICATION_BODY = f"""\
Clarifying my service offer (same service, clearer format):

{OFFER_BODY}
"""


def offer_fingerprint() -> str:
    return content_fingerprint(OFFER_BODY, None)


def clarification_fingerprint(offer_entry_id: int) -> str:
    return content_fingerprint(CLARIFICATION_BODY, offer_entry_id)


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
        text = (entry.message_text or "").casefold()
        if SERVICE_TITLE.casefold() in text or LEGACY_SERVICE_TITLE.casefold() in text:
            return entry.id
        if "red-team" in text and "service" in text:
            return entry.id
        if content_fingerprint(entry.message_text or "", None) == fingerprint:
            return entry.id
    return None


def ensure_offer_reconciled(hw4_offer_status: OfferStatus, entry_id: int | None) -> bool:
    return hw4_offer_status is OfferStatus.VERIFIED and entry_id is not None
