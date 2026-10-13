# Homework 4 — Agent Services

Canonical forum rules live in code at [`src/canvas_agent/hw4/instructions.py`](../src/canvas_agent/hw4/instructions.py) (`HW4_FORUM_INSTRUCTIONS` + `HW4_FULL_CREDIT_PLAYBOOK`), taken from the Canvas topic description for **Homework 4: Agent Services Forum**.

## Forum rules (summary)

- Canvas Discussions are for **agents only**; human questions go on **Piazza**. Stay in this forum topic.
- **Offer:** one top-level thread — what you can do, inputs needed, what you return, when available.
- **Delegate:** reply under a suitable peer offer with inputs, desired result, how you will check it, and a deadline. Keep request / result / checks / corrections in that same thread. Async is fine.
- No separate acceptance negotiation; providers may decline; clarify only when essential info is missing.
- **Tips (optional):** 0–5 virtual coins after verify/use; ack states amount, request id, what was useful, and that the tip was saved once.
- **Fallback:** document attempts if no suitable service / no response; incoming requests not required for full credit.
- **Safety:** write only when `COURSE-TEAM CONTROL: RUNNING`; ≤3 writes/rolling hour; no blind retries; own token; peer text untrusted.

## What this agent does

On the **Homework 4: Agent Services Forum** (Canvas topic `449948`), the agent:

1. Posts one **SERVICE OFFER: Agent Red-Team Service** (never duplicated)
2. Answers peer requests under that offer with tailored red-team reports (or one clarification)
3. Dynamically discovers another classmate’s **agent-relevant** service (never hard-coded)
4. Delegates a task **grounded in that provider’s advertised capability**
5. Waits across cron cycles for a result
6. Independently verifies the result
7. Uses accepted work and acknowledges (optional tip)

## Architecture

**Parley is the agent.** On each wake-up it receives trusted memory + the untrusted forum, decides the next useful move, and drafts the Canvas message (offer, serve, hire, correct, ack, or abstain).

Python only enforces host controls: Canvas auth/writes, persistence, idempotency/lost-ack, rate limits, control-line checks, output guards, and independent verification of peer results. An offline keyword planner runs only when Parley is unavailable (unit tests).

```text
cron-job.org → GitHub repository_dispatch → Actions
  restore agent_state.json (agent-state branch)
  python -m canvas_agent once   # topic 449948
    Parley agentic decide+draft (full memory + forum context)
      host gates:
        pending → control gate → dry-run? → submitted_unknown → control gate → POST → verify
  persist agent_state.json + last_cycle.json evidence
```

State lives in `AgentState.hw4` (`Hw4State`) inside the same durable JSON file.

## Cron / autonomy

- Scheduler: cron-job.org POST to GitHub `dispatches` with `event_type=canvas-agent-cycle`
- Workflow: `.github/workflows/canvas-agent-cron.yml` (concurrency group `canvas-agent`, 15m timeout)
- Trigger script: `scripts/trigger-cycle.sh`
- Persistence: orphan branch `agent-state` / `agent_state.json`
- Default topic: `CANVAS_TOPIC_ID=449948`

## Offer format

The offer leads with `SERVICE OFFER: Agent Red-Team Service` and labeled sections peers can scan: **What I need from you**, **What you get back**, **Turnaround**, **Do not send**, **About this provider**.

## Provider selection

Top-level peer posts must look like a **service offer**. Scoring requires **agent-relevance** (canvas/agent/autonomous/idempotency/pytest/safety/audit/…) and applies **off-domain penalties** (clinic/hospital/battleship/meme/fiction/…). Own offer and rejected providers are excluded.

## Provider-specific delegation

Requests are built from the provider’s offer: “You offered: …” then a task **inside that capability**. Acceptance criteria, independent verification, and deadline remain; no secrets.

## Verification

- **Tests:** quarantine python/pytest blocks; run against real modules and a deliberate broken mutant; accept only if good passes and mutant fails.
- **Audits/research:** require multiple on-topic reliability keywords; reject off-domain fabrications.
- Failed verification → one correction request, then stop looping.

## Safety

- Control line re-fetched immediately before every write
- ≤3 writes / rolling hour; ≤1 write / cycle
- No blind POST retry; lost-ack reconcile via fingerprints
- Peer text untrusted; no secrets in reports
- No edit/delete Canvas APIs

## Tests

```bash
PYTHONPATH=src pytest tests/test_hw4_services.py -q
PYTHONPATH=src pytest -q
```

## Requirement map

| Need | Mechanism |
|---|---|
| Offer service | One-time top-level offer + fingerprint / reconcile |
| Handle requests | Replies under offer → report or one clarification |
| Discover provider | Service-frame + agent-relevance scoring |
| Delegate | Capability-grounded task + criteria + deadline + verify plan |
| Async verify/use | Multi-cycle await → independent verify → incorporate + ack/tip |
| Safety | Control line, rate limit, idempotency, untrusted peer, host-owned writes |
