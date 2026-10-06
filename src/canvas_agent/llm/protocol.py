"""LLM advisor protocol — decide and draft only."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from canvas_agent.models import AdvisorDecision, DiscussionSnapshot


@runtime_checkable
class LLMAdvisor(Protocol):
    def decide_and_draft(
        self,
        snapshot: DiscussionSnapshot,
        *,
        agent_user_id: int | None,
        prior_fingerprints: list[str],
        prior_messages: list[str],
    ) -> AdvisorDecision:
        """Return abstain or a proposed post. Must not perform side effects."""
