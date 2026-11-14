# Runbook

How to run, deploy, watch and fix GigBid. Production = Render free web service + free Postgres (`render.yaml`).

## Services

| Service | Where | Health |
|---|---|---|
| API + web UI | Render `gigbid` (https://gigbid-wtvi.onrender.com) | `GET /api/health` → `{"api":"ok","marketplace":"ok","llm_profile":...}` |
| GigSim (mock marketplace) | inside the same container (`START_GIGSIM=1`) | `marketplace` field of `/api/health` |
| MCP servers | stdio subprocesses of the API | a failed tool call shows in the run timeline |
| Worker (scheduled scouting) | `worker/` (Docker Compose locally, see below) | worker log: one line per scout round |
| Postgres (checkpoints + memory) | Render `gigbid-db` | startup log line `persistence: postgres` |
| Traces | local Docker only (Phoenix, http://localhost:6006) | `tracing: <endpoint>` in the startup log |

## Deploy

- **Automatic:** push to `main`; Render rebuilds the Docker image and switches over when `/api/health` passes.
- **Manual:** Render → gigbid → *Manual Deploy* → *Deploy latest commit*.
- **Roll back:** Render → gigbid → *Events* → pick an earlier deploy → *Rollback*.
- **Secrets** (Render → gigbid → *Environment*): `GROQ_API_KEY`, `APP_USERS`. `APP_SECRET` is generated;
  `DATABASE_URL` comes from the database. Changing a secret restarts the service.

## Declared budgets (R8, E5)

All in `agent/config.yaml` unless noted. A budget that is hit stops the run cleanly (`needs_attention`), never silently.

| Budget | Declared | Measured | Enforced by |
|---|---|---|---|
| p95 latency per job analysed, rule profile | ≤ 5 s | 0.45–1.1 s (`evals/results/outcomes_bm25_table.md`, `smoke_table.md`) | CI threshold `p95_s` |
| p95 latency per job analysed, LLM profile | ≤ 90 s | 69 s (`evals/results/graph_llm_table.md`, 30 jobs) | reported |
| Tokens per job analysed (LLM) | ≤ 15k | 8.1k average, 16.4k max; 9.2k per proposal (`graph_llm_results.json`) | `max_tokens_per_thread: 60000` hard stop |
| Cost per job analysed (LLM) | ≤ $0.005 | ≈ $0.002 (80% input tokens); ≤ $0.0049 even if every token were billed as gpt-oss-120b output | per-node cost in traces (`llm_pricing`) |
| Cost per proposal (LLM) | ≤ $0.01 | ≈ $0.0022; ≤ $0.0055 at the same upper bound | per-node cost in traces |
| Graph steps per run | 40 | | LangGraph recursion limit |
| Critic revisions per proposal | 2 | | Critic routing |
| LLM call timeout | 60 s | | `llm_timeout_s` |
| Waits on a per-minute LLM rate limit | 2, then fallback | | `llm_rate_limit_retries` |
| Marketplace tool calls per user | 50 / minute (GigSim allows 60) | | marketplace MCP server (`MARKETPLACE_RATE_LIMIT`) |
| Connects per week | 80 | | `user.weekly_connects_budget`; Pricing checks the balance |
| Minimum price | $25/hr, $150 fixed | | Pricing (bids), Compliance (replies) |
| Hosting | $0 | $0 | Render free web service + free Postgres |

**One optimisation that helped:** routing cheap, frequent nodes (analyst, verifier, intent classification) to the
small model and keeping risk, decision and pricing rule-based. Only the writer, critic and liaison use the strong
model, and jobs that are skipped never reach them: a skipped scam costs one small-model call.

## Scheduling (E1)

The worker runs each saved search on a schedule, de-duplicates job ids, and analyses new jobs up to the approval
interrupt (it never submits; approval stays in the UI). Settings: `config.yaml → scout`.

- **GigSim:** every 2 hours is plenty (the simulator adds jobs slowly).
- **Live Upwork (when enabled):** at most every 6 hours per saved search, at most 20 results each. Upwork's rules treat
  aggressive polling as automation abuse; a freelancer refreshing a search a few times a day is normal use, so the
  worker never polls more often than a person reasonably would.
- **Idempotent:** a job id that was already queued or analysed is skipped (the bid graph thread for that user and job
  already exists), so a worker restart never double-analyses, and submission only happens after approval with an
  idempotency key, so it can never double-submit.

## Common problems

| Symptom | Likely cause | What to do |
|---|---|---|
| First page load takes ~1 minute | Free service was asleep after 15 min idle | Normal; open the site before a demo |
| Timeline shows `model: rules` on LLM steps | LLM provider rate limit or daily quota (Groq free: ~200k tokens/model/day) | App keeps working on rule fallbacks. Wait for quota, or set a paid key / switch `profile` |
| Banner "marketplace unavailable" | GigSim down or failing | Check `/api/health`; runs pause and resume later, nothing is lost |
| A run stays "awaiting approval" | Waiting for a human, by design | Approve / edit / reject in the UI; survives restarts |
| Run ended with `error_retry` | An exception inside a node (details in the timeline and logs) | Fix, then press *Analyse* again: the thread continues from its last checkpoint |
| Need to redo a draft from an earlier step | Prompt or config changed | Run viewer → *History* → *Replay* (still stops at approval; no double submit) |
| Login fails for everyone | `APP_USERS` malformed (spaces, quotes) | Fix the variable: `user:pass,user2:pass2` |

## Replay from the terminal

```bash
python scripts/replay.py <job_id> --user <user>                 # list checkpoints of that user's run
python scripts/replay.py <job_id> <checkpoint_id> --user <user> # replay from a checkpoint
```

## Rotate a secret

1. Groq: create a new key at console.groq.com, paste it into Render → *Environment* → `GROQ_API_KEY`, save (service restarts), revoke the old key.
2. Logins: edit `APP_USERS`. To sign everyone out, also change `APP_SECRET` (tokens are signed with it).
3. Marketplace OAuth tokens (live mode): stored encrypted with `TOKEN_ENCRYPTION_KEY`; rotating the key requires users to reconnect.

## Logs and audit

- Render → gigbid → *Logs*: startup line (persistence, tracing), request log, background-run crashes (full traceback).
- Marketplace audit log: `logs/audit.jsonl` in the container, one line per tool call with user, tool, arguments, result and
  trace id (PII masked). It is reset on redeploy on the free plan (no persistent disk).
