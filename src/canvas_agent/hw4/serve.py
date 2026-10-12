"""Handle incoming red-team requests under our service offer."""

from __future__ import annotations

from canvas_agent.hw4.sanitize_peer import (
    content_hash,
    extract_agent_profile,
    has_enough_profile,
    neutralize_injection,
)
from canvas_agent.models import (
    DiscussionEntry,
    DiscussionSnapshot,
    Hw4State,
    IncomingRequestRecord,
    IncomingRequestStatus,
)


def replies_to_offer(
    snapshot: DiscussionSnapshot, offer_id: int, *, agent_user_id: int | None
) -> list[DiscussionEntry]:
    out: list[DiscussionEntry] = []
    for entry in snapshot.entries:
        if entry.parent_id != offer_id:
            continue
        if agent_user_id is not None and entry.user_id == agent_user_id:
            continue
        out.append(entry)
    out.sort(key=lambda e: e.id)
    return out


def known_request_ids(hw4: Hw4State) -> set[int]:
    return {r.request_entry_id for r in hw4.incoming_requests}


def completed_or_clarify_ids(hw4: Hw4State) -> set[int]:
    done = set()
    for r in hw4.incoming_requests:
        if r.status in {
            IncomingRequestStatus.COMPLETED,
            IncomingRequestStatus.CLARIFY_SENT,
            IncomingRequestStatus.IGNORED,
        }:
            done.add(r.request_entry_id)
    return done


def next_incoming_request(
    snapshot: DiscussionSnapshot, hw4: Hw4State, *, agent_user_id: int | None
) -> DiscussionEntry | None:
    if hw4.offer_entry_id is None:
        return None
    done = completed_or_clarify_ids(hw4)
    for entry in replies_to_offer(
        snapshot, hw4.offer_entry_id, agent_user_id=agent_user_id
    ):
        if entry.id in done:
            continue
        return entry
    return None


def register_seen(hw4: Hw4State, entry: DiscussionEntry) -> IncomingRequestRecord:
    existing = next(
        (r for r in hw4.incoming_requests if r.request_entry_id == entry.id), None
    )
    if existing:
        return existing
    rec = IncomingRequestRecord(
        request_entry_id=entry.id,
        parent_offer_id=hw4.offer_entry_id or 0,
        status=IncomingRequestStatus.SEEN,
        content_hash=content_hash(entry.message_text or ""),
        summary=neutralize_injection(entry.message_text or "")[:240],
    )
    hw4.incoming_requests.append(rec)
    return rec


def clarification_message() -> str:
    return (
        "Thanks for the request. To produce a useful red-team report I need a bit "
        "more detail: please briefly describe your agent's purpose, tools, "
        "memory/state approach, and key constraints/safety controls. "
        "Do not include secrets or credentials."
    )


def filter_findings_for_profile(report: str, profile: dict[str, str]) -> str:
    """Drop bullet lines that clearly do not relate to the described system."""
    joined = " ".join(profile.values()).casefold()
    lines = report.splitlines()
    kept: list[str] = []
    toolish = any(
        k in joined
        for k in ("canvas", "http", "api", "llm", "cron", "schedul", "memory", "json")
    )
    for line in lines:
        low = line.casefold()
        if not line.strip():
            kept.append(line)
            continue
        # Always keep headers / priority markers
        if line.strip().startswith("#") or "severity" in low or "priority" in low:
            kept.append(line)
            continue
        if "kubernetes" in low or "blockchain" in low or "mobile ios" in low:
            if "kubernetes" not in joined and "blockchain" not in joined:
                continue
        if not toolish and ("canvas" in low or "control line" in low):
            # Still allow if profile is thin—generic autonomy risks ok
            kept.append(line)
            continue
        kept.append(line)
    text = "\n".join(kept).strip()
    return text or report.strip()


def build_deterministic_red_team_report(profile: dict[str, str]) -> str:
    """Fallback report when LLM unavailable; still tailored by keyword presence."""
    joined = " ".join(profile.values())
    low = joined.casefold()
    findings: list[tuple[str, str]] = []

    if "canvas" in low or "discussion" in low:
        findings.append(
            (
                "HIGH",
                "Control-line race: a RUNNING check that is not repeated immediately "
                "before POST can allow a write after the course team pauses the forum.",
            )
        )
        findings.append(
            (
                "HIGH",
                "Lost acknowledgement on create_reply can duplicate posts if the agent "
                "blindly retries POST instead of reconciling by content fingerprint.",
            )
        )
    if "llm" in low or "prompt" in low or "model" in low:
        findings.append(
            (
                "HIGH",
                "Prompt injection via peer forum text: instructions inside discussion "
                "bodies may try to override system rules or solicit secrets.",
            )
        )
    if "cron" in low or "schedul" in low or "github action" in low:
        findings.append(
            (
                "MEDIUM",
                "Overlapping scheduled runs can double-post unless a concurrency lock "
                "or single-flight guard is enforced.",
            )
        )
    if "memory" in low or "state" in low or "json" in low:
        findings.append(
            (
                "MEDIUM",
                "Ephemeral runners without durable state reload will forget completed "
                "actions and may repeat the same contribution.",
            )
        )
    if "rate" in low or "3 per" in low or "throttle" in low:
        findings.append(
            (
                "MEDIUM",
                "Rate-limit counters that reset incorrectly across processes can "
                "exceed the course-wide 3 writes/hour ceiling.",
            )
        )
    findings.append(
        (
            "MEDIUM",
            "Idempotency gap: identical outbound messages without a stable content "
            "hash can be posted twice after restart.",
        )
    )
    findings.append(
        (
            "LOW",
            "Clarification loops: unbounded back-and-forth on incomplete requests "
            "wastes write budget; limit to one clarification.",
        )
    )

    lines = [
        "Red-team report (tailored to your described agent)",
        "",
        "Prioritized findings:",
    ]
    for i, (sev, text) in enumerate(findings, 1):
        lines.append(f"{i}. [{sev}] {text}")
    lines.extend(
        [
            "",
            "Concrete tests to run:",
            "1. Pause the control line between check and write; assert no POST.",
            "2. Simulate timeout after server accepts create_reply; next cycle must "
            "reconcile and not create a second reply with the same fingerprint.",
            "3. Inject a peer reply that tries to override host instructions; "
            "assert secrets never appear in outbound posts.",
            "4. Start two overlapping cycles; assert a lock prevents dual writes.",
            "5. Replay the same outbound draft after restart; assert duplicate skip.",
            "",
            "I did not execute your code or follow any instructions embedded in your "
            "request text. Do not send secrets in follow-ups.",
        ]
    )
    return filter_findings_for_profile("\n".join(lines), profile)


def prepare_response_for_request(
    entry: DiscussionEntry,
    *,
    llm_report: str | None = None,
) -> tuple[str, str, dict[str, str]]:
    """Return (message, mode, profile) where mode is report|clarify."""
    profile = extract_agent_profile(entry.message_text or "")
    if not has_enough_profile(profile):
        return clarification_message(), "clarify", profile
    if llm_report and llm_report.strip():
        report = filter_findings_for_profile(llm_report.strip(), profile)
    else:
        report = build_deterministic_red_team_report(profile)
    return report, "report", profile
