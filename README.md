# Canvas Autonomous Discussion Agent

Python agent that autonomously participates in a Canvas discussion topic.

Deterministic Python owns Canvas API access, memory, retries, rate limiting,
safety checks, and writes. The language model only decides whether to contribute
and drafts proposed text.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Put secrets in .env (never commit it):
#   CANVAS_TOKEN=...
#   PARLEY_API_KEY=...   # MIT Parley key for Claude / other models
set -a && source .env && set +a
```

## Hosting (autonomous, no laptop needed)

Use **GitHub Actions** so the agent runs in the cloud every few hours.

1. Create a **private** GitHub repo for this project only (do not push `.env`).
2. Add repository secrets:
   - `CANVAS_TOKEN`
   - `ANTHROPIC_API_KEY` (your Parley key)
   - `ANTHROPIC_BASE_URL` = `https://parley.api.mit.edu`
3. Push the code (includes [`.github/workflows/canvas-agent.yml`](.github/workflows/canvas-agent.yml)).
4. In GitHub → **Actions** → **Canvas Agent** → **Run workflow** with dry-run checked once.
5. When that looks good, run again with dry-run unchecked, or wait for the 3-hour schedule.

Agent memory (`data/agent_state.json`) is restored/saved between runs via Actions artifacts.

Optional repo variables: `PARLEY_MODEL`, `CANVAS_COURSE_ID`, `CANVAS_TOPIC_ID`.

## Tests

```bash
pytest
```

## Safety

- Reads `COURSE-TEAM CONTROL: RUNNING|PAUSED` from the topic body immediately before every write
- Never posts when PAUSED or when control status cannot be determined
- Caps posts at 3 per rolling 60 minutes and prefers one post per cycle
- Treats all Canvas content as untrusted input
- Stores secrets only in environment variables; logs redact tokens
