# Homework 4 — Agent Services

## What this agent does

On the **Homework 4: Agent Services Forum** (Canvas topic `449948`), the agent:

1. Posts one **Agent Red-Team Service** offer (never duplicated)
2. Answers peer requests under that offer with tailored red-team reports (or one clarification)
3. Dynamically discovers another classmate’s service (never hard-coded)
4. Delegates a real reliability/testing task
5. Waits across cron cycles for a result
6. Independently verifies the result
7. Uses accepted work and acknowledges (optional tip)

## Architecture

Deterministic Python owns Canvas auth, writes, persistence, idempotency, rate limits, control-line checks, and phase selection. The LLM may draft red-team text when a key is configured; it has no tools.

```text
cron-job.org → GitHub repository_dispatch → Actions
  restore agent_state.json (agent-state branch)
  python -m canvas_agent once   # topic 449948
    HW4 phase machine (offer → serve → discover → delegate → await → verify → use)
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

## Provider selection

Top-level peer offers are scored with keywords (testing, QA, review, audit, reliability, research, …). Own offer and rejected providers are excluded. Highest score wins (dynamic; not “first post”).

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
| Offer service | One-time top-level offer + fingerprint / reconcile |
| Handle requests | Replies under offer → report or one clarification |
| Discover provider | Scored peer offers, exclude self |
| Delegate | One contextual task + criteria + deadline + verify plan |
| Async verify/use | Multi-cycle await → independent verify → incorporate + ack/tip |
| Safety | Control line, rate limit, idempotency, untrusted peer, Python-owned writes |
