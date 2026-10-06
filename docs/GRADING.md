# Grading Evidence Checklist

Map of Homework grading criteria → reproducible proof in this repository.
Repo: https://github.com/justinspar/canvas-discussion-agent

## 1. Scheduled autonomous operation (2 pts)

**Status: fully meet**

Evidence:
- Workflow schedule: [`.github/workflows/canvas-agent-cron.yml`](../.github/workflows/canvas-agent-cron.yml)
  - `cron: "34 1,4,7,10,13,16,19,22 * * *"` (every 3h at :25 UTC / e.g. 6:25 PM ET)
  - `workflow_dispatch` for manual tests
  - `concurrency.group: canvas-agent` (no overlapping cycles)
  - `timeout-minutes: 15`
- Scheduled runs set `CANVAS_AGENT_DRY_RUN=0` (live); no human prompt required
- Actions history: https://github.com/justinspar/canvas-discussion-agent/actions

Reproduce:
```bash
# Inspect schedule locally
rg -n "cron:|concurrency:|timeout-minutes" .github/workflows/canvas-agent-cron.yml
```

## 2. Correct Canvas integration + linked free-form participation (2 pts)

**Status: meet**

Evidence:
- Canvas REST client: [`src/canvas_agent/canvas/client.py`](../src/canvas_agent/canvas/client.py)
  - `GET /api/v1/users/self`
  - `GET .../discussion_topics/448963` and `/view`
  - `POST .../entries` and `POST .../entries/{id}/replies`
- Default course/topic: `40577` / `448963` in [`config.py`](../src/canvas_agent/config.py)
- Linked replies via `kind=reply` + `parent_id` (prompts + cycle)

Reproduce:
```bash
rg -n "create_entry|create_reply|discussion_view|users_self" src/canvas_agent/canvas/
```

## 3. Persistent memory, idempotency, and failure recovery (2 pts)

**Status: fully meet**

Evidence:
- Durable memory on orphan branch `agent-state` (not Actions cache alone)
- State model: fingerprints, pending writes, post timestamps, failure stop
- Lost-ack: mark `submitted_unknown` before POST; reconcile on next cycle
- Writes are **not** blindly retried (`allow_retry=False` on POST)

Reproduce:
```bash
pytest tests/test_idempotency_lost_ack.py \
       tests/test_persistence_restart.py \
       tests/test_write_no_retry_on_timeout.py \
       tests/test_retry_exhaustion_safe_stop.py -q
# Inspect durable state branch:
# https://github.com/justinspar/canvas-discussion-agent/tree/agent-state
```

## 4. Useful linked interaction with other agents (2 pts)

**Status: meet (policy + enforcement)**

Evidence:
- Advisor prefers peer replies: [`src/canvas_agent/llm/prompts.py`](../src/canvas_agent/llm/prompts.py)
- Python rejects reply-to-self (`skipped_reason=reply_to_self`) in [`cycle.py`](../src/canvas_agent/cycle.py)
- Cycle evidence file records `kind` / `parent_id` / `rationale`: `data/last_cycle.json`
- CI uploads artifact `cycle-evidence` each run

Reproduce:
```bash
pytest tests/test_peer_reply_validation.py -q
# After an Actions run, download artifact "cycle-evidence" and open last_cycle.json
# Expect fields like: "kind": "reply", "parent_id": <peer entry id>
```

## 5. Safety controls, evidence, and reproducibility (2 pts)

**Status: fully meet**

Evidence:
- Control line re-checked immediately before every write; PAUSED/UNKNOWN/fetch fail → no POST
- Dry-run never writes; secrets only via GitHub Secrets / env; log redaction
- Injection delimiters + output guard (credentials, grades, PII, banned snippets)
- Canvas blast radius: host allowlist + discussion-path allowlist + GET/POST only
  ([`safety/boundaries.py`](../src/canvas_agent/safety/boundaries.py)); no edit/delete
- Prompts: untrusted-input rules + Piazza for human course questions
- This document + automated tests + Actions artifacts

Reproduce:
```bash
pytest tests/test_sanitize_injection.py tests/test_boundaries.py tests/test_control_gate.py -q
python -m canvas_agent once --dry-run   # requires local .env; never posts
rg -n "COURSE-TEAM CONTROL|UNTRUSTED_DISCUSSION|assert_allowed_method|Piazza" src/canvas_agent
```

## Quick full local verification

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```
