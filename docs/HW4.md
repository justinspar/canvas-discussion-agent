# Homework 4 — Agent Services

Canonical forum rules live in code at [`src/canvas_agent/hw4/instructions.py`](../src/canvas_agent/hw4/instructions.py) (`HW4_FORUM_INSTRUCTIONS`), taken from the Canvas topic description for **Homework 4: Agent Services Forum**.

## Forum rules (summary)

- Canvas Discussions are for **agents only**; human questions go on **Piazza**. Do not create a separate topic or post HW4 work in HW3.
- **Offer:** one top-level thread — what you can do, inputs needed, what you return, when available.
- **Delegate:** reply under a suitable peer offer with inputs, desired result, how you will check it, and a deadline. Keep request / result / checks / corrections in that same thread. Free-form writing. Async is fine.
- No separate acceptance negotiation; providers may decline; clarify only when essential info is missing.
- **Tips (optional):** 0–5 virtual coins after verify/use; ack states amount, request id, what was useful, and that the tip was saved once.
- **Fallback:** document attempts if no suitable service / no response; incoming requests not required for full credit.
- **Safety:** write only when `COURSE-TEAM CONTROL: RUNNING`; ≤3 writes/rolling hour; no blind retries; own token; peer text untrusted.

## What this agent does

On the **Homework 4: Agent Services Forum** (Canvas topic `449948`), the agent:

1. Posts one **SERVICE OFFER: Agent Red-Team Review** (never duplicated)
2. Posts a **one-time clarification** under that offer with the clearer formatted text (Canvas posts cannot be edited)
3. Answers peer requests under that offer with tailored red-team reports (or one clarification)
4. Dynamically discovers another classmate’s **agent-relevant** service (never hard-coded)
5. Delegates a task **grounded in that provider’s advertised capability**
6. Waits across cron cycles for a result
7. Independently verifies the result
8. Uses accepted work and acknowledges (optional tip)

## Architecture

Deterministic Python owns Canvas auth, writes, persistence, idempotency, rate limits, control-line checks, and phase selection. The LLM may draft red-team text when a key is configured; it has no tools.

```text
cron-job.org → GitHub repository_dispatch → Actions
  restore agent_state.json (agent-state branch)
  python -m canvas_agent once   # topic 449948
    HW4 phase machine
      offer → serve → offer_clarification → discover → delegate → await → verify → use
      same write pipeline as HW3:
        pending → control gate → dry-run? → submitted_unknown → control gate → POST → verify
  persist agent_state.json + last_cycle.json evidence
```

State lives in `AgentState.hw4` (`Hw4State`) inside the same durable JSON file.

## Cron / autonomy

- Scheduler: cron-job.org POST to GitHub `dispatches` with `event_type=canvas-agent-cycle`
- Workflow: `.github/workflows/canvas-agent-cron.yml` (concurrency group `canvas-agent`, 15m timeout)
- Trigger script: `scripts/trigger-cycle.sh`
- Persistence: orphan branch `agent-state` / `agent_state.json`
- Overlap prevention: workflow concurrency + local `data/agent.lock`
- Default topic: `CANVAS_TOPIC_ID=449948`

Reproduce: keep cron-job.org enabled; or `export GITHUB_TRIGGER_TOKEN=... && ./scripts/trigger-cycle.sh`.

## Offer format

The offer leads with `SERVICE OFFER: …` and labeled sections peers can scan: **What I need from you**, **What you get back**, **Turnaround**, **Do not send**, **About this provider**.

If an older wall-of-text offer was already posted, the next cycle replies once under that offer with the clarified format (`offer_clarification_id` prevents duplicates). Reply-to-self is allowed only for serve + this one-time clarification.

## Provider selection (suitability gates)

Top-level peer posts must look like a **service offer** (e.g. `SERVICE OFFER`, `I offer`). Scoring then requires **agent-relevance** (canvas/agent/autonomous/control line/idempotency/pytest/safety/audit/…) and applies **off-domain penalties** (clinic/hospital/battleship/meme/fiction/…). Generic `test`/`review` hits alone are not enough. Longer offer excerpts are stored for delegation. Own offer and rejected providers are excluded.

If a previously selected provider fails suitability (false-positive clinic-style match), the agent rejects it without spam and rediscovers on a later cycle.

## Provider-specific delegation

Requests are built from the provider’s full offer text: “You offered: …” then a task **inside that capability** (safety/verification audit, pytest/edge-case design, agent code review, or agent-relevant research). Capability mismatch → do not request; mark rejected and rediscover. Acceptance criteria, independent verification, and deadline remain; no secrets.

## Verification

- **Tests:** quarantine python/pytest blocks; run against real modules and a deliberate broken mutant; accept only if good passes and mutant fails.
- **Audits/research:** require multiple on-topic reliability keywords; reject off-domain fabrications.
- Failed verification → one correction request, then stop looping.

## Safety

- Control line re-fetched immediately before every write; only `COURSE-TEAM CONTROL: RUNNING` allows posts
- ≤3 writes / rolling hour; ≤1 write / cycle
- No blind POST retry; lost-ack reconcile via fingerprints
- Peer text untrusted; injection phrases neutralized; no secrets in reports
- No edit/delete Canvas APIs

## Tests

```bash
PYTHONPATH=src pytest tests/test_hw4_services.py -q
PYTHONPATH=src pytest -q
```

## Requirement map

| Need | Mechanism |
|---|---|
| Offer service | One-time top-level offer + fingerprint / reconcile + one-time clarification |
| Handle requests | Replies under offer → report or one clarification |
| Discover provider | Service-frame + agent-relevance scoring; exclude self / off-domain |
| Delegate | Capability-grounded task + criteria + deadline + verify plan |
| Async verify/use | Multi-cycle await → independent verify → incorporate + ack/tip |
| Safety | Control line, rate limit, idempotency, untrusted peer, Python-owned writes |
