"""Parley-backed HW4 reasoning paths (fake OpenAI client)."""

from __future__ import annotations

import json

from canvas_agent.hw4.delegate import build_request_message
from canvas_agent.hw4.discover import select_provider
from canvas_agent.hw4.llm_helpers import rank_providers, reason_service_request
from canvas_agent.models import ProviderCandidate


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = type("M", (), {"content": content})()


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls = 0

    def create(self, **kwargs):  # noqa: ANN003
        self.calls += 1
        return type("R", (), {"choices": [_FakeChoice(self._content)]})()


class _FakeClient:
    def __init__(self, content: str) -> None:
        self.chat = type("C", (), {"completions": _FakeCompletions(content)})()


def test_rank_providers_uses_parley_json() -> None:
    client = _FakeClient(json.dumps({"entry_id": 42, "rationale": "best fit"}))
    eid = rank_providers(
        [
            {"entry_id": 41, "title": "A", "excerpt": "game"},
            {"entry_id": 42, "title": "B", "excerpt": "pytest for agents"},
        ],
        our_needs="need tests",
        client=client,
        model="bedrock/claude-sonnet-5",
    )
    assert eid == 42
    assert client.chat.completions.calls == 1


def test_select_provider_prefers_llm_rank() -> None:
    cands = [
        ProviderCandidate(entry_id=1, score=99, title_snippet="high keyword", offer_excerpt="x"),
        ProviderCandidate(
            entry_id=2,
            score=1,
            title_snippet="llm pick",
            offer_excerpt="SERVICE OFFER: pytest for agents",
        ),
    ]
    client = _FakeClient(json.dumps({"entry_id": 2, "rationale": "matches"}))
    chosen = select_provider(
        cands, llm_client=client, llm_model="bedrock/claude-sonnet-5"
    )
    assert chosen is not None
    assert chosen.entry_id == 2


def test_reason_service_request_and_build_message() -> None:
    payload = {
        "suitable": True,
        "rationale": "they audit draft requests",
        "task": "Audit this DRAFT SERVICE REQUEST:\n---\nhello\n---",
        "criteria": "Need ACCEPT/REVISE/REJECT",
    }
    client = _FakeClient(json.dumps(payload))
    result = reason_service_request(
        provider_offer="SERVICE OFFER: audit requests",
        draft_service_request="DRAFT service request\nTask: tests",
        our_needs="need audit",
        client=client,
        model="bedrock/claude-sonnet-5",
    )
    assert result is not None
    assert result["suitable"] is True
    assert "DRAFT" in result["task"]

    auditor = ProviderCandidate(
        entry_id=9, score=10, title_snippet="audit", offer_excerpt="audit offer/request"
    )
    # LLM path used inside build_request_message
    client2 = _FakeClient(json.dumps(payload))
    built = build_request_message(
        auditor,
        offer_text="Service offer: reviews offer, request, or returned result. ACCEPT/REVISE/REJECT",
        peer_candidates=[
            auditor,
            ProviderCandidate(
                entry_id=8,
                score=5,
                title_snippet="pytest",
                offer_excerpt="SERVICE OFFER: pytest edge-case for autonomous agents",
            ),
        ],
        llm_client=client2,
        llm_model="bedrock/claude-sonnet-5",
    )
    assert built is not None
    msg, task, criteria, _ = built
    assert "DRAFT" in task
    assert "ACCEPT" in criteria.casefold() or "accept" in criteria.casefold()
    assert "You offered:" in msg
