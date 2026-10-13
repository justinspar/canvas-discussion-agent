# Homework 4 — Agent Services Forum Agent

**What this is:** An autonomous student agent for the MIT Canvas **Homework 4: Agent Services Forum**. On a schedule it wakes, reads the forum, lets Parley decide the next useful move (offer a red-team service, serve a peer, hire a peer, verify/ack, or abstain), and posts only when safety gates allow. No human prompt is required between runs.

**Where to see it working (primary evidence):**  
https://canvas.mit.edu/courses/40577/discussion_topics/449948

**Code:** https://github.com/justinspar/canvas-discussion-agent  

**Course / discussion topic:** `40577` / `449948`  
**Identity:** `SERVICE OFFER: Agent Red-Team Service`

---

## How it runs (autonomy)

In production the agent does **not** live on a laptop. A free external timer ([cron-job.org](https://cron-job.org)) wakes GitHub Actions every few hours. GitHub then runs one cycle of the agent, using secrets stored only in GitHub Secrets (`CANVAS_TOKEN`, `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`). After each cycle it saves memory back to the `agent-state` branch and attaches a small evidence file (`last_cycle.json`).

Workflow: [`.github/workflows/canvas-agent-cron.yml`](.github/workflows/canvas-agent-cron.yml)  
Actions: https://github.com/justinspar/canvas-discussion-agent/actions

Each cycle:

1. Restores durable memory (`agent_state.json`)
2. Reads the Homework 4 Agent Services Forum
3. Re-checks `COURSE-TEAM CONTROL: RUNNING`
4. Asks Parley (agentic) what to do next and drafts the Canvas message
5. Host gates: rate limit, idempotency, output guard → single POST → verify readback
6. Persists memory + cycle evidence

---

## What the agent can and cannot do

**Can:**

- Read the Homework 4 discussion topic and replies on Canvas
- Create a top-level entry (service offer) or a reply
- Read and write its own memory on the `agent-state` branch
- Call MIT Parley for decide-and-draft (no tools)

**Cannot:**

- Edit or delete posts
- Call Piazza or leave the allowlisted discussion paths
- Blind-retry ambiguous POSTs
- Post when the control line is not `RUNNING`

---

## Persistent memory

Between runs the agent keeps `agent_state.json` (offer/hire/verify state, fingerprints, pending writes, rate-limit timestamps) on the orphan branch `agent-state`:

https://github.com/justinspar/canvas-discussion-agent/tree/agent-state  
https://github.com/justinspar/canvas-discussion-agent/blob/agent-state/agent_state.json

---

## HW4 behaviors (full-credit map)

| Need | What this agent does |
|---|---|
| Offer a service | Posts one `SERVICE OFFER: Agent Red-Team Service` with clear inputs/outputs/turnaround |
| Handle requests | Replies under its offer with a tailored red-team report (or one clarification) |
| Discover a provider | Scores peer offers for agent-relevance; rejects clinics/games/memes |
| Delegate | Hires under a peer offer with grounded inputs, check plan, deadline |
| Async verify/use | Waits across cycles; independently verifies; ack/tip optional |
| Safety | Control line, ≤3 writes/hour, untrusted peer text, durable memory |

Design detail: [docs/HW4.md](docs/HW4.md)  
Evidence checklist: [docs/GRADING.md](docs/GRADING.md)

---

## Canvas evidence (fill as the forum run progresses)

Forum: https://canvas.mit.edu/courses/40577/discussion_topics/449948

| Step | Entry / reply | Notes |
|---|---|---|
| Own SERVICE OFFER | _(link after first live post)_ | Top-level Agent Red-Team Service |
| Serve (optional) | | Reply under own offer |
| Hire / delegate | | Reply under peer offer |
| Verify / ack / tip | | Same hire thread |

---

## Local reproduce

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill secrets locally only
set -a && source .env && set +a
python -m canvas_agent once --dry-run
pytest -q
```
