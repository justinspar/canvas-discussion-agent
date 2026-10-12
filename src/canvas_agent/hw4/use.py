"""Incorporate accepted peer work and draft acknowledgment / tip."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from canvas_agent.hw4.verify import VerifyOutcome


def apply_accepted_tests(
    outcome: VerifyOutcome, *, repo_root: Path | None = None
) -> str:
    """Write accepted peer tests into tests/hw4_peer/. Returns relative path."""
    if not outcome.accepted or not outcome.test_source:
        return ""
    root = repo_root or Path(__file__).resolve().parents[3]
    dest_dir = root / "tests" / "hw4_peer"
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Keep package importable
    init = dest_dir / "__init__.py"
    if not init.exists():
        init.write_text("# Peer-verified HW4 tests\n", encoding="utf-8")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = dest_dir / f"test_peer_accepted_{stamp}.py"
    dest.write_text(outcome.test_source, encoding="utf-8")
    try:
        return str(dest.relative_to(root))
    except ValueError:
        return str(dest)


def acknowledgment_message(
    *,
    accepted: bool,
    tip_amount: int = 0,
    useful_summary: str = "",
) -> str:
    if not accepted:
        return (
            "Thanks — I independently checked the result and could not accept it yet. "
            "Please see my prior correction note if present."
        )
    tip_line = ""
    if tip_amount > 0:
        tip_line = (
            f"\n\nTip: {tip_amount} virtual coin(s) for {useful_summary or 'useful verified work'}."
        )
    return (
        "Acknowledgment: I independently verified your result and have incorporated "
        f"the accepted work{(' (' + useful_summary + ')') if useful_summary else ''}."
        f"{tip_line}"
    )


def correction_message(outcome: VerifyOutcome) -> str:
    return (
        "Correction request (one-time): I could not accept the previous result. "
        f"Verification method={outcome.method}; outcome={outcome.outcome}. "
        "Please revise with concrete, on-topic deliverables only (no secrets, no shell). "
        f"Evidence summary: {outcome.evidence[:400]}"
    )


def tip_amount_for_outcome(outcome: VerifyOutcome) -> int:
    if not outcome.accepted:
        return 0
    if outcome.method == "pytest_mutant":
        return 4
    if outcome.method == "audit_crosscheck":
        return 3
    return 2
