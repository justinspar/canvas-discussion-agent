"""Safety package."""

from canvas_agent.safety.control import explain_block, may_post
from canvas_agent.safety.output_guard import OutputGuardError, validate_decision
from canvas_agent.safety.sanitize import format_discussion_for_llm, sanitize_entry_text

__all__ = [
    "explain_block",
    "may_post",
    "OutputGuardError",
    "validate_decision",
    "format_discussion_for_llm",
    "sanitize_entry_text",
]
