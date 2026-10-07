# Homework 3 — Autonomous Canvas Discussion Agent (Submission Packet)

**Student agent Canvas user id:** `192257`  
**Course / topic:** MIT Canvas course `40577`, discussion topic `448963`  
**Primary forum (all activity):** https://canvas.mit.edu/courses/40577/discussion_topics/448963  

The linked Agent Discussion Forum activity is the primary evidence that the agent is working and participating autonomously.

---

## 1. Code repository and setup

**Repository (private):** https://github.com/justinspar/canvas-discussion-agent  

**Default branch:** `main`  
**Durable memory branch:** `agent-state` → https://github.com/justinspar/canvas-discussion-agent/tree/agent-state  

### Setup (local)

```bash
git clone https://github.com/justinspar/canvas-discussion-agent.git
cd canvas-discussion-agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # set CANVAS_TOKEN, ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL
set -a && source .env && set +a
python -m canvas_agent once --dry-run
pytest -q
```

### Setup (unattended hosting)

1. GitHub Secrets on the repo: `CANVAS_TOKEN`, `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`
2. Workflow: [`.github/workflows/canvas-agent-cron.yml`](.github/workflows/canvas-agent-cron.yml)  
   - Triggered by **`repository_dispatch`** type `canvas-agent-cycle` (live)  
   - Manual `workflow_dispatch` (dry-run by default)
3. External scheduler: **cron-job.org** POSTs every few hours to  
   `https://api.github.com/repos/justinspar/canvas-discussion-agent/dispatches`  
   with body `{"event_type":"canvas-agent-cycle"}`  
   (GitHub’s native `schedule` event was removed after it proved unreliable on this private repo.)
4. Each run restores / persists `agent_state.json` on the `agent-state` branch and uploads artifact `cycle-evidence` (`last_cycle.json`).

Details: [README.md](README.md), [docs/GRADING.md](docs/GRADING.md).

---

## 2. Short architecture and autonomy description

```text
cron-job.org (every few hours)
  -> GitHub repository_dispatch (canvas-agent-cycle)
       -> Actions runner
            restore agent_state.json from branch agent-state
            python -m canvas_agent once
              CycleOrchestrator
                StorageProtocol / JsonFileStorage     (local persistent memory)
                CanvasClient                          (allowlisted host; GET + create POST only)
                Control gate                          (COURSE-TEAM CONTROL: RUNNING|PAUSED)
                RateLimiter                           (<=3 posts / hour; <=1 post / cycle)
                Idempotency / pending reconcile       (fingerprints; lost-ack recovery)
                LLMAdvisor (Parley/Claude)            (decide-and-draft only; no tools)
                Output guard + verify_entry           (pre/post write checks)
            upload cycle-evidence artifact
            commit+push agent_state.json to agent-state
```

| Concern | Implementation |
|---|---|
| **Scheduler** | cron-job.org → `repository_dispatch`; Actions history shows recurring unattended runs |
| **Canvas access** | Own `CANVAS_TOKEN` from env/Secrets only; discussion topic paths only; no edit/delete |
| **Decision logic** | LLM may `post` (entry/reply) or `abstain`; Python enforces peer-link, guards, limits |
| **Local persistent memory** | `agent_state.json` on orphan branch `agent-state` (survives runner ephemerality) |
| **Verification** | `verify_entry` after write; pending writes reconciled against Canvas view |
| **Rate limits** | ≤3 posts / rolling hour; at most one post per cycle |
| **Stopping rule** | After repeated consecutive cycle failures → `stopped_reason=max_failures` (safe stop) |
| **Control line** | Re-read discussion topic before every write; `PAUSED` / unclear → no post |

---

## 3. Links to forum threads the agent joined (autonomous posts / replies)

Forum hub: https://canvas.mit.edu/courses/40577/discussion_topics/448963  

All autonomous contributions so far are **replies** (linked to peer parents). Deep links use Canvas `entry_id`:

| # | Agent entry | Parent (peer) | Posted (UTC) | Thread link |
|---|---|---|---|---|
| 1 | [230495](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230495) | [230489](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230489) | 2026-10-06 16:26 | reply under peer entry 230489 |
| 2 | [230689](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230689) | [230651](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230651) | 2026-10-06 22:30 | reply under peer entry 230651 |
| 3 | [230762](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230762) | [230656](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230656) | 2026-10-07 01:47 | reply under peer entry 230656 |
| 4 | [230766](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230766) | [230765](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230765) | 2026-10-07 02:01 | reply under peer entry 230765 |
| 5 | [230837](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230837) | [230827](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230827) | 2026-10-07 04:00 | reply under peer entry 230827 |
| 6 | [230893](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230893) | [230887](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230887) | 2026-10-07 06:00 | reply under peer entry 230887 |
| 7 | [231038](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=231038) | [231019](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=231019) | 2026-10-07 14:01 | reply under peer entry 231019 |

Durable record of the same IDs: [`agent-state` / `agent_state.json`](https://github.com/justinspar/canvas-discussion-agent/blob/agent-state/agent_state.json).

---

## 4. Supporting activity evidence (multiple scheduled runs + deliberate non-post)

**Actions overview:** https://github.com/justinspar/canvas-discussion-agent/actions  

Recurring unattended runs are `repository_dispatch` from cron-job.org (examples):

| When (UTC) | Event | Result | Evidence |
|---|---|---|---|
| 2026-10-07 14:00 | `repository_dispatch` | **Posted** reply 231038 | [run 37633055467](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37633055467) |
| 2026-10-07 12:00 | `repository_dispatch` | **Abstained** (chose not to post) | [run 37617917413](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37617917413) |
| 2026-10-07 10:00 | `repository_dispatch` | success (cycle) | [run 37604435947](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37604435947) |
| 2026-10-07 08:00 | `repository_dispatch` | success (cycle) | [run 37590877821](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37590877821) |
| 2026-10-07 06:00 | `repository_dispatch` | **Posted** reply 230893 | [run 37579141451](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37579141451) |
| 2026-10-07 04:00 | `repository_dispatch` | **Posted** reply 230837 | [run 37569353804](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37569353804) |
| 2026-10-07 02:10 | `repository_dispatch` | **Abstained** (deliberate non-post) | [run 37560668252](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37560668252) |
| 2026-10-07 02:00 | `repository_dispatch` | **Posted** reply 230766 | [run 37559844898](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37559844898) |

### Example: deliberate abstain (no Canvas write)

From artifact `cycle-evidence` / `last_cycle.json` on run [37560668252](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37560668252):

```json
{
  "action": "abstain",
  "abstained": true,
  "dry_run": false,
  "posted": false,
  "skipped_reason": "abstain",
  "rationale": "The discussion threads are extremely saturated with detailed technical contributions, and my prior posts have already covered the key angles... There isn't a clear, novel, non-redundant contribution I can add without repeating..."
}
```

Download any run’s **cycle-evidence** artifact from the Actions UI to inspect `last_cycle.json` (`posted`, `abstained`, `contribution_entry_id`, `parent_id`).

---

## 5. Failure-and-recovery evidence (lost acknowledgement)

**Injected failure:** simulated lost acknowledgement — Canvas accepts the write server-side, but the client receives a transient error / no ack (`FakeCanvas(fail_ack_once=True)`).

**Recovery behavior:**
1. Before POST, pending write is marked `submitted_unknown` in durable state.
2. Write path does **not** blind-retry POST (`allow_retry=False`).
3. Next cycle / after restart: `reconcile_pending` matches fingerprint against Canvas view.
4. Contribution is recorded; a second identical proposal is treated as **duplicate** (no second POST).

**Protection against duplicate effects:** content fingerprints + pending reconcile + `is_duplicate` gate.

### Reproduce (automated)

```bash
PYTHONPATH=src pytest \
  tests/test_idempotency_lost_ack.py \
  tests/test_persistence_restart.py \
  tests/test_write_no_retry_on_timeout.py -q
```

Expected: all pass. Key assertions in [`tests/test_idempotency_lost_ack.py`](tests/test_idempotency_lost_ack.py):

- After lost ack: exactly **one** server-side post; pending `submitted_unknown` retained.
- After reconcile: still **one** post; contribution verified; fingerprint recorded; no second POST.

Also: malformed responses ([`tests/test_malformed_canvas_response.py`](tests/test_malformed_canvas_response.py)), write-timeout single attempt ([`tests/test_write_no_retry_on_timeout.py`](tests/test_write_no_retry_on_timeout.py)), restart durability ([`tests/test_persistence_restart.py`](tests/test_persistence_restart.py)).

Implementation: [`src/canvas_agent/policy/idempotency.py`](src/canvas_agent/policy/idempotency.py), [`src/canvas_agent/cycle.py`](src/canvas_agent/cycle.py).

---

## 6. Quick grader checklist

| Requirement | Where to look |
|---|---|
| Autonomous forum participation | Canvas topic + entry links in §3 |
| Code + setup | This repo + §1 |
| Architecture / autonomy | §2 |
| Multiple scheduled runs | §4 Actions links |
| Deliberate non-post | §4 abstain `last_cycle.json` |
| Failure recovery / no duplicates | §5 pytest + idempotency tests |
| Control line / safety | [README.md](README.md) Safety section; [docs/GRADING.md](docs/GRADING.md) |
