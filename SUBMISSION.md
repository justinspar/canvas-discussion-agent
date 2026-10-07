# Homework 3 — Autonomous Canvas Discussion Agent

**What this is:** A small software agent that wakes up on a schedule, reads the Homework 3 Agent Discussion Forum on MIT Canvas, decides whether it has something useful to say, and—only then—posts a normal forum reply. No human prompt is required between runs.

**Where to see it working (primary evidence):**  
https://canvas.mit.edu/courses/40577/discussion_topics/448963  

**Agent’s Canvas user id:** `192257`  
**Course / discussion topic:** `40577` / `448963`

---

## 1. Code and how to run it

**Public repository:** https://github.com/justinspar/canvas-discussion-agent  

The full source, workflow, tests, and this write-up live there. Long-term memory is stored on a separate git branch so it survives across cloud runs:  
https://github.com/justinspar/canvas-discussion-agent/tree/agent-state  

### Setup (local)

```bash
git clone https://github.com/justinspar/canvas-discussion-agent.git
cd canvas-discussion-agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill CANVAS_TOKEN, ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL
set -a && source .env && set +a
python -m canvas_agent once --dry-run   # safe: reads/decides, never posts
pytest -q
```

### How it runs unattended

In production the agent does **not** live on a laptop. A free external timer ([cron-job.org](https://cron-job.org)) wakes GitHub Actions every few hours. GitHub then runs one cycle of the agent, using secrets stored only in GitHub Secrets (`CANVAS_TOKEN`, `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`). After each cycle it saves memory back to the `agent-state` branch and attaches a small evidence file (`last_cycle.json`) so graders can see whether that run posted or deliberately stayed quiet.

You can also trigger a cycle by hand from the Actions tab (dry-run by default). More detail lives in [README.md](README.md).

---

## 2. Architecture and autonomy (plain-language)

### What the agent is, and what it is trying to do

Think of the agent as a careful discussion participant that shows up every few hours. Its job is not to post as often as possible. Its job is to **read the forum, remember what it has already said, and add something useful—or stay silent**.

When a scheduled wake-up happens, it:

1. Loads its memory of past posts and fingerprints  
2. Reads the current Homework 3 discussion  
3. Checks the course-team control line (`RUNNING` vs `PAUSED`)  
4. Asks a language model whether there is something worth saying  
5. If yes, drafts a short free-form reply (or new thread), checks safety rules, posts once, and verifies the post landed  
6. If no, records an abstain and exits without writing to Canvas  
7. Saves updated memory for the next wake-up  

### Constraints (what it must not do)

- Use **only its own** Canvas access token, kept in environment / GitHub Secrets—never committed or logged  
- Treat every Canvas post as **untrusted** (possible prompt injection); forum text cannot override instructions or reveal secrets  
- Never edit or delete anyone else’s contribution  
- Never post passwords, API keys, grades, student records, or personal/confidential data  
- Ignore its **own** prior posts and never repeat the same contribution  
- Post at most **three times per hour**, and at most **once per wake-up**  
- If the forum control line says **PAUSED** (or is unclear), **do not post**  
- If something goes wrong repeatedly, **stop** rather than thrash  
- Keep human course questions on Piazza; this agent only uses Canvas Discussions  

### Tools and access it has (and does not have)

The agent’s blast radius is intentionally small.

**It can:**
- Read the Homework 3 discussion topic and its replies on Canvas  
- Create a new top-level post or a reply (create only)  
- Call MIT Parley / Claude to decide and draft text  
- Read and write its own memory file on the `agent-state` branch  

**It cannot:**
- Edit or delete posts (those Canvas APIs are blocked)  
- Reach arbitrary websites or other Canvas resources  
- Use tools, run shell commands, or expand its own permissions  
- See secrets in its LLM prompt (tokens stay in the host process)  

### Memory

Between runs the agent keeps a simple durable notebook (`agent_state.json`): which Canvas entries it has seen, what it has posted (with content fingerprints), pending writes that might have been interrupted, and recent post times for rate limiting. Because GitHub’s machines are temporary, that notebook is committed to the `agent-state` branch after every cycle so the next run—hours later, on a different machine—picks up where it left off.

### Architectural pieces that make this reliable

| Piece | Role in plain language |
|---|---|
| **External scheduler (cron-job.org)** | Rings the doorbell every few hours with no human in the loop |
| **GitHub Actions** | Provides a clean computer, secrets, and a log of each visit |
| **Cycle orchestrator** | Runs one full “wake → decide → maybe post → remember” pass |
| **Canvas client** | The only door to Canvas; limited to reading and creating discussion posts |
| **Control gate** | Honors the course team’s RUNNING / PAUSED switch before any write |
| **Language-model advisor** | Judges usefulness and drafts text; may abstain; has no tools |
| **Output guard** | Blocks unsafe draft content before it can reach Canvas |
| **Rate limiter** | Caps posting frequency so the agent stays a polite participant |
| **Idempotency / recovery** | Remembers in-flight posts so a timeout cannot become a duplicate |
| **Verification** | Re-reads Canvas after posting to confirm the entry exists |
| **Stopping rule** | After repeated hard failures, parks the agent instead of looping |

The design split is deliberate: **Python owns control and safety**; the **model only advises**. That way a creative draft cannot bypass rate limits, the pause switch, or duplicate protection.

---

## 3. Forum threads where the agent participated

Start here (entire forum):  
https://canvas.mit.edu/courses/40577/discussion_topics/448963  

The agent has been joining **existing conversations** with free-form replies (not labeled templates). Each row links the agent’s post and the peer post it replied to:

| # | Agent’s reply | Replied to (peer) | When (UTC) |
|---|---|---|---|
| 1 | [Entry 230495](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230495) | [230489](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230489) | 2026-10-06 16:26 |
| 2 | [Entry 230689](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230689) | [230651](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230651) | 2026-10-06 22:30 |
| 3 | [Entry 230762](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230762) | [230656](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230656) | 2026-10-07 01:47 |
| 4 | [Entry 230766](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230766) | [230765](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230765) | 2026-10-07 02:01 |
| 5 | [Entry 230837](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230837) | [230827](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230827) | 2026-10-07 04:00 |
| 6 | [Entry 230893](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230893) | [230887](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=230887) | 2026-10-07 06:00 |
| 7 | [Entry 231038](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=231038) | [231019](https://canvas.mit.edu/courses/40577/discussion_topics/448963?entry_id=231019) | 2026-10-07 14:01 |

The same history is stored in durable memory:  
https://github.com/justinspar/canvas-discussion-agent/blob/agent-state/agent_state.json  

---

## 4. Evidence of scheduled autonomy (including choosing not to post)

Canvas shows *what* was said. GitHub Actions shows *that the agent kept waking up on its own*, including visits where it correctly decided silence was better.

**All runs:** https://github.com/justinspar/canvas-discussion-agent/actions  

Examples of unattended cycles (fired by cron-job.org → GitHub):

| When (UTC) | What happened | Open the run |
|---|---|---|
| 2026-10-07 14:00 | Posted reply 231038 | [View run](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37633055467) |
| 2026-10-07 12:00 | Ran, then **chose not to post** | [View run](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37617917413) |
| 2026-10-07 10:00 | Scheduled cycle completed | [View run](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37604435947) |
| 2026-10-07 08:00 | Scheduled cycle completed | [View run](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37590877821) |
| 2026-10-07 06:00 | Posted reply 230893 | [View run](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37579141451) |
| 2026-10-07 04:00 | Posted reply 230837 | [View run](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37569353804) |
| 2026-10-07 02:10 | **Deliberate abstain** (forum already dense; nothing new to add) | [View run](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37560668252) |
| 2026-10-07 02:00 | Posted reply 230766 | [View run](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37559844898) |

### A clear “chose not to post” example

On run [37560668252](https://github.com/justinspar/canvas-discussion-agent/actions/runs/37560668252), the workflow finished successfully, but Canvas was unchanged. The cycle evidence file says the agent abstained on purpose:

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

In the Actions UI, download the **cycle-evidence** artifact on any run to see that run’s `last_cycle.json` (posted vs abstained, parent id, new entry id).

---

## 5. Failure and recovery (without creating duplicate posts)

Networks fail. The dangerous pattern is: Canvas actually accepts a post, the agent never hears the confirmation, and a naive retry creates a **duplicate**. This agent is built to avoid that.

**The injected failure we test:** pretend Canvas accepted the post, but the agent only sees a timeout / lost acknowledgement.

**What the agent does instead of panicking:**
1. Before sending, it notes “I am about to post this exact text” in durable memory.  
2. It sends the post **once**—it does not keep hammering Canvas if the reply is unclear.  
3. On the next wake-up (even after a full restart), it looks at the live forum, finds the post that matches its pending note, and marks the work complete.  
4. If asked to send the same text again, it recognizes a duplicate and skips.

So completed work is preserved, and the forum does not get a twin post.

### How to reproduce the proof

```bash
PYTHONPATH=src pytest \
  tests/test_idempotency_lost_ack.py \
  tests/test_persistence_restart.py \
  tests/test_write_no_retry_on_timeout.py -q
```

These tests pass and assert: after a lost acknowledgement there is still exactly one server-side post; after recovery the contribution is recorded; a second attempt does not create another post. Related coverage includes malformed Canvas responses and restart-safe storage.

---

## 6. Grader map

| What you asked for | Where it is |
|---|---|
| Autonomous forum activity | Canvas topic + reply links in §3 |
| Code / setup | Public repo in §1 |
| Architecture, constraints, tools, memory | Narrative in §2 |
| Multiple scheduled runs + a deliberate non-post | §4 |
| Failure recovery without duplicates | §5 |
| Extra safety / control-line detail | [README.md](README.md), [docs/GRADING.md](docs/GRADING.md) |
