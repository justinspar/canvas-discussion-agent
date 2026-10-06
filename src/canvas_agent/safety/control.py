"""Control-line safety gate for Canvas writes."""

from __future__ import annotations

from canvas_agent.models import ControlStatus


def may_post(control_status: ControlStatus) -> bool:
    """Return True only when the course team explicitly set RUNNING."""
    return control_status is ControlStatus.RUNNING


def explain_block(control_status: ControlStatus) -> str:
    if control_status is ControlStatus.PAUSED:
        return "control_paused"
    if control_status is ControlStatus.UNKNOWN:
        return "control_unknown"
    return "ok"
