"""Write grader-facing cycle evidence (no secrets)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from canvas_agent.models import CycleResult


def write_cycle_evidence(path: Path, result: CycleResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rationale = (result.rationale or "")[:500]
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": result.action
        or (
            "error"
            if result.error
            else "post"
            if result.posted or result.dry_run
            else "abstain"
            if result.abstained
            else "skip"
        ),
        "kind": result.kind.value if result.kind else None,
        "parent_id": result.parent_id,
        "abstained": result.abstained,
        "dry_run": result.dry_run,
        "posted": result.posted,
        "skipped_reason": result.skipped_reason,
        "rationale": rationale,
        "error": result.error,
        "contribution_entry_id": (
            result.contribution.canvas_entry_id if result.contribution else None
        ),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
