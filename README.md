# Canvas Autonomous Discussion Agent

Python agent that autonomously participates in an MIT Canvas discussion topic
via GitHub Actions (and optionally a local process).

Deterministic Python owns Canvas API access, secrets, memory, retries, rate
limiting, safety checks, and writes. The language model only decides whether
there is something useful to contribute and drafts proposed text.

## Architecture

```text
GitHub Actions (every 3h)
  -> restore agent_state.json from orphan branch `agent-state`
  -> python -m canvas_agent once
       CycleOrchestrator
         StorageProtocol (JsonFileStorage)
         CanvasClient (allowlisted host, GET + create POST only)
         SafetyGate (control line RUNNING/PAUSED)
         RateLimiter (<=3 posts / 60m, <=1 per cycle)
         IdempotencyGuard (fingerprints + pending reconcile)
         LLMAdvisor (Parley/Claude decide-and-draft only)
  -> commit+push updated agent_state.json to `agent-state`
```

## Required GitHub Secrets

Set these in the private repo (Settings → Secrets and variables → Actions):

| Secret | Purpose |
|---|---|
| `CANVAS_TOKEN` | Canvas personal access token |
| `ANTHROPIC_API_KEY` | MIT Parley API key |
| `ANTHROPIC_BASE_URL` | `https://parley.api.mit.edu` |

Never commit secrets. Local development uses a gitignored `.env` (see `.env.example`).

Optional repo variables: `PARLEY_MODEL`, `CANVAS_COURSE_ID`, `CANVAS_TOPIC_ID`.

## Official participation rules (Homework 3)

- Free-form forum writing; may join existing threads and/or start new ones
- Post only when useful; ignore own posts; no repeated contributions
- Scheduled every few hours; durable memory across runs; ≤3 posts / hour
- Retries with backoff; verify each write; stop after repeated failures
- Before every write: re-read the Canvas **discussion topic** control line;
  if `COURSE-TEAM CONTROL: PAUSED` (or unclear), **do not post**

## Safety and boundaries

| Requirement | How this agent enforces it |
|---|---|
| Own Canvas token only, in env/secret manager | `CANVAS_TOKEN` from env or GitHub Secrets; never hardcoded |
| Never commit, display, log, or submit the token | `.gitignore` for `.env`; log redaction; Config/`CycleResult` redact; evidence omits secrets |
| Do not edit or delete another person’s contribution | Client allowlists **GET + create POST only**; PUT/PATCH/DELETE blocked; no edit/delete endpoints |
| No passwords, API keys, PMs, grades, student records, PII, confidential data | System prompt + `output_guard` blocks secretish / grade / PII patterns before POST |
| Treat every Canvas post as untrusted (prompt injection) | Discussion text wrapped in `<<<UNTRUSTED_DISCUSSION>>>`; LLM has **no tools**; host instructions win |
| Small blast radius | Allowlisted Canvas host + discussion paths only; LLM chat completions only; GHA `contents`/`actions` write limited; ≤3 posts/hour; dry-run |
| Canvas Discussions only; human Qs on Piazza | Prompt instructs Piazza for human course questions; agent never calls Piazza |

While the course team marks the forum as setup/API testing, posting stays gated
by the control line (`PAUSED` / non-`RUNNING` → no write). Manual dry-run remains
the default for `workflow_dispatch`.

[`.github/workflows/canvas-agent-cron.yml`](.github/workflows/canvas-agent-cron.yml):

- **Primary schedule:** external cron (cron-job.org) → `repository_dispatch` type `canvas-agent-cycle` (live)
- Backup: GitHub `schedule` every 3h at :34 UTC (often delayed/dropped on private Free plans)
- `workflow_dispatch` for manual dry-run / live tests
- `concurrency.group: canvas-agent` with `cancel-in-progress: false`
- `timeout-minutes: 15`
- Credentials only from GitHub Secrets / env vars

`repository_dispatch` and GitHub `schedule` runs are live (`CANVAS_AGENT_DRY_RUN=0`).
Manual `workflow_dispatch` defaults to dry-run.

### External cron (recommended — unattended)

GitHub’s built-in `schedule` event has not been firing for this private repo.
Use a free HTTP cron service to ping GitHub every few hours instead:

1. Create a **classic GitHub PAT** (not your Canvas token):
   https://github.com/settings/tokens/new  
   Scopes: `repo` + `workflow`. Note it once; do not commit it.
2. Sign up at **https://cron-job.org** (free).
3. Create a cron job:
   - **URL:** `https://api.github.com/repos/justinspar/canvas-discussion-agent/dispatches`
   - **Schedule:** every 3 hours (e.g. `25 */3 * * *`)
   - **Request method:** POST
   - **Headers:**
     - `Authorization: Bearer <YOUR_PAT>`
     - `Accept: application/vnd.github+json`
     - `Content-Type: application/json`
   - **Body:** `{"event_type":"canvas-agent-cycle"}`
4. Save → Enable. First fire can be “Run now” in cron-job.org to verify.
5. Confirm in Actions that the run event is **`repository_dispatch`**.

Local smoke test (same API):

```bash
export GITHUB_TRIGGER_TOKEN=ghp_...   # PAT from step 1
./scripts/trigger-cycle.sh
```

## Persistent memory across GitHub Actions runners

GitHub-hosted runners are ephemeral. Correctness-critical memory is **not**
stored only in Actions cache/artifacts.

Durable state lives on the orphan git branch **`agent-state`** as
`agent_state.json` (kept off `main` history):

1. Workflow restores `data/agent_state.json` from `origin/agent-state`
2. Agent reads/writes only through `StorageProtocol` / `JsonFileStorage`
3. Workflow commits and pushes the updated file back to `agent-state`

State includes: seen entry IDs, contribution records, content fingerprints,
pending writes (including lost-ack), post timestamps for rate limiting,
failure counters / `stopped_reason`.

## Control-line safety

Immediately before **every** Canvas write, the agent re-fetches the topic and
parses the first plain-text line of the description (`message` field):

- `COURSE-TEAM CONTROL: RUNNING` → write may proceed if other checks pass
- `COURSE-TEAM CONTROL: PAUSED` → do not write
- missing / malformed / ambiguous / fetch failure → **fail closed**, do not write

## Retries and backoff

- **Reads:** bounded exponential backoff with jitter on timeouts / 429 / 5xx
- **Writes:** **single attempt only**. Timeouts or ambiguous responses raise
  an ambiguous-write error; the agent does **not** blind-retry POST
- After repeated full-cycle failures (`max_consecutive_failures`, default 3),
  the agent sets `stopped_reason=max_failures` and refuses further posts

## Idempotency

Before posting, Python checks content fingerprints and open pending writes.
Each intended write gets a client `request_id` and is marked
`submitted_unknown` before POST. Completed actions are recorded with Canvas
entry IDs after verified readback. Duplicates are suppressed even if the LLM
proposes the same text again.

## Lost-acknowledgement recovery

If Canvas accepts a write but the client loses the response:

1. Pending write stays `submitted_unknown` in durable state
2. Next run restores state and reads Canvas `/view`
3. Matching own post by fingerprint is confirmed; no second POST

### Demonstrate for homework

```bash
pytest tests/test_idempotency_lost_ack.py tests/test_persistence_restart.py -q
```

These simulate: accepted write → lost ack → restart → reconcile → no duplicate.

## Dry-run mode

```bash
python -m canvas_agent once --dry-run
# or: CANVAS_AGENT_DRY_RUN=1 python -m canvas_agent once
```

Performs read / filter / decide, logs the would-be action, never POSTs to Canvas,
never prints secrets.

On GitHub: Actions → Canvas Agent → Run workflow → leave dry-run checked.

## Local setup and tests

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill CANVAS_TOKEN + ANTHROPIC_* locally only
set -a && source .env && set +a
python -m canvas_agent once --dry-run
pytest
```

## Homework requirements mapping (1–6)

1. **Autonomous forum participation** — scheduled GHA cycles read the discussion and may post/reply.
2. **Useful contributions only** — LLM may abstain; Python enforces rate limits and dedup.
3. **Safety / control** — RUNNING/PAUSED gate immediately before every write; fail closed.
4. **No secret leakage / untrusted input** — secrets from env/Secrets only; Canvas text delimited as untrusted; LLM has no tools; PUT/PATCH/DELETE and non-discussion paths blocked.
5. **Reliability** — durable `agent-state` branch memory; idempotent writes; lost-ack reconcile; read retries; no blind POST retry.
6. **Observability / ops** — dry-run, tests, concurrency lock, timeout, safe-stop after repeated failures.

See **[docs/GRADING.md](docs/GRADING.md)** for the 2-pt grading checklist with reproducible evidence pointers.

## Residual risks

- GitHub cron can be delayed on free/private plans
- Canvas or Parley outages pause progress until the next cycle
- State-branch push races are mitigated by workflow `concurrency`, not by distributed locks beyond that
