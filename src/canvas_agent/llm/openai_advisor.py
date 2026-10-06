"""Hosted chat advisor (MIT Parley / OpenAI-compatible)."""

from __future__ import annotations

import json
import logging
from typing import Any

from canvas_agent.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from canvas_agent.models import AdvisorDecision, DiscussionSnapshot, WriteKind
from canvas_agent.safety.sanitize import format_discussion_for_llm

logger = logging.getLogger(__name__)

DEFAULT_PARLEY_BASE_URL = "https://parley.api.mit.edu/v1"
DEFAULT_PARLEY_MODEL = "bedrock/claude-sonnet-5"


class ParleyAdvisor:
    """Decide-and-draft via Parley's OpenAI-compatible Chat Completions API.

    Use this with a Parley API key (sk-parley-v1-...) to reach Anthropic Claude
    and other models hosted by MIT Parley.
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_PARLEY_MODEL,
        base_url: str = DEFAULT_PARLEY_BASE_URL,
        client: Any | None = None,
    ) -> None:
        if client is not None:
            self._client = client
        else:
            from openai import OpenAI

            self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def decide_and_draft(
        self,
        snapshot: DiscussionSnapshot,
        *,
        agent_user_id: int | None,
        prior_fingerprints: list[str],
        prior_messages: list[str],
    ) -> AdvisorDecision:
        discussion_block = format_discussion_for_llm(
            snapshot, agent_user_id=agent_user_id, exclude_own=True
        )
        user_prompt = build_user_prompt(
            discussion_block=discussion_block,
            prior_fingerprints=prior_fingerprints,
            prior_messages=prior_messages,
        )
        # Parley/Claude: ask for JSON in the prompt; response_format is not
        # reliably supported across all Parley models.
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": user_prompt
                    + "\n\nRespond with ONLY a valid JSON object, no markdown.",
                },
            ],
        )
        content = response.choices[0].message.content or "{}"
        return self._parse_decision(content)

    @staticmethod
    def _parse_decision(content: str) -> AdvisorDecision:
        text = content.strip()
        if text.startswith("```"):
            # Strip accidental markdown fences
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract the first JSON object
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    data = json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    logger.warning("LLM returned non-JSON; abstaining")
                    return AdvisorDecision(action="abstain", rationale="invalid_json")
            else:
                logger.warning("LLM returned non-JSON; abstaining")
                return AdvisorDecision(action="abstain", rationale="invalid_json")

        action = data.get("action", "abstain")
        if action != "post":
            return AdvisorDecision(
                action="abstain", rationale=str(data.get("rationale") or "abstain")
            )

        kind_raw = data.get("kind")
        kind = None
        if kind_raw == "entry":
            kind = WriteKind.ENTRY
        elif kind_raw == "reply":
            kind = WriteKind.REPLY

        parent_id = data.get("parent_id")
        if parent_id is not None:
            try:
                parent_id = int(parent_id)
            except (TypeError, ValueError):
                parent_id = None

        return AdvisorDecision(
            action="post",
            kind=kind,
            parent_id=parent_id,
            message=data.get("message"),
            rationale=str(data.get("rationale") or ""),
        )


# Back-compat alias used by older imports/tests
OpenAIAdvisor = ParleyAdvisor


class StubAdvisor:
    """Deterministic advisor for tests."""

    def __init__(self, decision: AdvisorDecision | None = None) -> None:
        self.decision = decision or AdvisorDecision(
            action="abstain", rationale="stub"
        )
        self.calls = 0

    def decide_and_draft(
        self,
        snapshot: DiscussionSnapshot,
        *,
        agent_user_id: int | None,
        prior_fingerprints: list[str],
        prior_messages: list[str],
    ) -> AdvisorDecision:
        self.calls += 1
        return self.decision
