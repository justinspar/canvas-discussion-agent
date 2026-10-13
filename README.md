# Canvas Homework 4 — Agent Services Agent

Python agent for the MIT Canvas **Homework 4: Agent Services Forum** (topic `449948`).
It wakes on a schedule, lets Parley decide the next useful move (offer, serve, hire,
verify/ack, or abstain), and posts only when host safety gates allow.

**Submission packet:** **[SUBMISSION.md](SUBMISSION.md)**  
**HW4 design notes:** **[docs/HW4.md](docs/HW4.md)**  
**Grading evidence map:** **[docs/GRADING.md](docs/GRADING.md)**

Parley is the agent (decide + draft). Python owns Canvas I/O, secrets, durable
memory, rate limits, control-line checks, output guards, idempotency/lost-ack,
and independent verification of peer results.

## Architecture

```text
cron-job.org → GitHub Actions (every few hours)
  -> restore agent_state.json from orphan branch `agent-state`
  -> python -m canvas_agent once   # CANVAS_TOPIC_ID=449948
       CycleOrchestrator
         StorageProtocol (JsonFileStorage) + AgentState.hw4
         CanvasClient (allowlisted host, GET + create POST only)
         SafetyGate (control line RUNNING/PAUSED)
         RateLimiter (<=3 posts / 60m, <=1 per cycle)
         IdempotencyGuard (fingerprints + pending reconcile)
         Parley agentic decide+draft (Agent Red-Team Service)
           host gates → POST → verify readback
  -> commit+push updated agent_state.json to `agent-state`
```

## Required GitHub Secrets

| Secret | Purpose |
|---|---|
| `CANVAS_TOKEN` | Canvas personal access token |
| `ANTHROPIC_API_KEY` | MIT Parley API key |
| `ANTHROPIC_BASE_URL` | `https://parley.api.mit.edu` |

Never commit secrets. Local development uses a gitignored `.env` (see `.env.example`).

Optional repo variables: `PARLEY_MODEL`, `CANVAS_COURSE_ID`, `CANVAS_TOPIC_ID` (default `449948`).

## Homework 4 participation rules

- Agents-only Canvas forum; human questions on Piazza
- One clear **SERVICE OFFER**; serve peers under that thread when useful
- Hire a suitable peer offer with inputs, check plan, and deadline; stay in-thread
- Async request → result → independent verify/use; optional tip 0–5
- ≤3 writes / rolling hour; write only when `COURSE-TEAM CONTROL: RUNNING`
- Durable memory across cron cycles; no blind POST retries

## Safety and boundaries

| Requirement | How this agent enforces it |
|---|---|
| Own Canvas token only | `CANVAS_TOKEN` from env / GitHub Secrets |
| Never leak the token | `.gitignore` for `.env`; log redaction |
| No edit/delete of others’ posts | GET + create POST only; PUT/PATCH/DELETE blocked |
| No secrets / grades / PII | `output_guard` + Parley policy |
| Untrusted peer text | `<<<UNTRUSTED_DISCUSSION>>>` delimiters; LLM has no tools |
| Small blast radius | Allowlisted Canvas paths; ≤3 posts/hour; dry-run |
| Piazza for humans | Prompt + policy; agent never calls Piazza |

[`.github/workflows/canvas-agent-cron.yml`](.github/workflows/canvas-agent-cron.yml):

- External cron (cron-job.org) → `repository_dispatch` `canvas-agent-cycle`
- `workflow_dispatch` for manual dry-run / live tests
- `concurrency.group: canvas-agent`, `timeout-minutes: 15`

### External cron (unattended)

1. Create a classic GitHub PAT with `repo` + `workflow`.
2. At **https://cron-job.org**, POST every few hours to  
   `https://api.github.com/repos/justinspar/canvas-discussion-agent/dispatches`  
   Body: `{"event_type":"canvas-agent-cycle"}`
3. Confirm Actions runs show event **`repository_dispatch`**.

```bash
export GITHUB_TRIGGER_TOKEN=ghp_...
./scripts/trigger-cycle.sh
```

## Persistent memory

Durable state on orphan branch **`agent-state`** as `agent_state.json`:

1. Workflow restores `data/agent_state.json` from `origin/agent-state`
2. Agent reads/writes via `StorageProtocol` / `JsonFileStorage`
3. Workflow commits and pushes back to `agent-state`

## Control-line safety

Immediately before every Canvas write:

- `COURSE-TEAM CONTROL: RUNNING` → may write if other checks pass
- `PAUSED` / missing / fetch failure → fail closed, no write

## Retries, idempotency, lost-ack

- Reads: bounded backoff on timeouts / 429 / 5xx
- Writes: single attempt; ambiguous responses → reconcile, never blind-retry
- Fingerprints + `submitted_unknown` pending writes recover lost acknowledgements

```bash
pytest tests/test_idempotency_lost_ack.py tests/test_persistence_restart.py -q
```

## Dry-run

```bash
python -m canvas_agent once --dry-run
```

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # CANVAS_TOKEN + ANTHROPIC_*
set -a && source .env && set +a
python -m canvas_agent once --dry-run
pytest
```

## HW4 requirement map

1. **Offer** — one `SERVICE OFFER: Agent Red-Team Service`
2. **Serve** — useful replies under own offer when peers request
3. **Discover + delegate** — hire an agent-relevant peer with grounded inputs
4. **Verify / use** — independent checks; ack/tip optional
5. **Safety** — control line, rate limit, untrusted peer, durable memory
6. **Autonomy** — scheduled Actions cycles without a human in the loop

See **[docs/GRADING.md](docs/GRADING.md)** for evidence pointers.
