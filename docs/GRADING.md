# Grading Evidence Checklist (Homework 4)

Map of Homework 4 Agent Services criteria → reproducible proof in this repository.  
Repo: https://github.com/justinspar/canvas-discussion-agent

**Full submission write-up:** [../SUBMISSION.md](../SUBMISSION.md)  
**Architecture:** [HW4.md](HW4.md)

## 1. Scheduled autonomous operation

**Status: meet**

Evidence:
- Workflow: [`.github/workflows/canvas-agent-cron.yml`](../.github/workflows/canvas-agent-cron.yml)
  - External cron → `repository_dispatch` (`canvas-agent-cycle`)
  - `workflow_dispatch` for manual tests; concurrency + 15m timeout
- Live runs set `CANVAS_AGENT_DRY_RUN=0`
- Actions: https://github.com/justinspar/canvas-discussion-agent/actions

```bash
rg -n "repository_dispatch|concurrency:|timeout-minutes" .github/workflows/canvas-agent-cron.yml
```

## 2. Correct Canvas integration on the HW4 forum

**Status: meet**

Evidence:
- Canvas REST client: [`src/canvas_agent/canvas/client.py`](../src/canvas_agent/canvas/client.py)
  - `GET /api/v1/users/self`
  - `GET .../discussion_topics/449948` and `/view`
  - `POST .../entries` and `POST .../entries/{id}/replies`
- Default course/topic: `40577` / `449948` in [`config.py`](../src/canvas_agent/config.py)
- Structured Canvas HTML on write (`to_canvas_html`)

```bash
rg -n "create_entry|create_reply|discussion_view|users_self|449948" src/canvas_agent/
```

## 3. Persistent memory, idempotency, and failure recovery

**Status: meet**

Evidence:
- Durable memory on orphan branch `agent-state`
- Fingerprints, pending writes, post timestamps, failure stop
- Lost-ack: `submitted_unknown` before POST; reconcile next cycle
- Writes are not blindly retried (`allow_retry=False` on POST)

```bash
pytest tests/test_idempotency_lost_ack.py \
       tests/test_persistence_restart.py \
       tests/test_write_no_retry_on_timeout.py \
       tests/test_retry_exhaustion_safe_stop.py -q
```

## 4. Agent Services behaviors (offer / hire / verify)

**Status: meet (policy + enforcement + tests)**

Evidence:
- Agentic Parley prompt + playbook: [`hw4/agentic.py`](../src/canvas_agent/hw4/agentic.py), [`hw4/instructions.py`](../src/canvas_agent/hw4/instructions.py)
- Offer identity: `SERVICE OFFER: Agent Red-Team Service` ([`hw4/offer.py`](../src/canvas_agent/hw4/offer.py))
- Discover/delegate/verify modules + [`tests/test_hw4_services.py`](../tests/test_hw4_services.py)
- Cycle evidence: `data/last_cycle.json` / Actions artifact `cycle-evidence`

```bash
pytest tests/test_hw4_services.py tests/test_hw4_agentic.py -q
```

## 5. Safety controls, evidence, and reproducibility

**Status: meet**

Evidence:
- Control line re-checked immediately before every write
- Dry-run never writes; secrets only via GitHub Secrets / env
- Injection delimiters + output guard (allowlisted HTML; strip scripts)
- Canvas blast radius: [`safety/boundaries.py`](../src/canvas_agent/safety/boundaries.py)
- Prompts: untrusted-input rules + Piazza for human course questions

```bash
pytest tests/test_sanitize_injection.py tests/test_boundaries.py tests/test_control_gate.py -q
python -m canvas_agent once --dry-run
rg -n "COURSE-TEAM CONTROL|UNTRUSTED_DISCUSSION|assert_allowed_method|Piazza" src/canvas_agent
```

## Quick full local verification

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```
