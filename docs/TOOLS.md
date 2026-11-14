# MCP Tools

All marketplace access goes through **one port** (`agent/marketplace_port.py`) with two adapters: `gigsim` (default) and `upwork` (live). Switch with `MARKETPLACE_MODE` in `.env`.

## Marketplace server (`mcp_servers/marketplace`), written by us

Auth: **stdio** = local user; **Streamable HTTP** (`--http`, port 8002) = bearer token (`MARKETPLACE_MCP_TOKENS`).
Every call: per-user rate limit (`MARKETPLACE_RATE_LIMIT`, 50/min, under GigSim's 60/min), append-only audit log `logs/audit.jsonl` (user, tool, args, result, trace id; emails and phones masked).

| Tool | Read / Write | readOnly | destructive | idempotent | Notes |
|---|---|---|---|---|---|
| `search_jobs(query, limit, offset)` | Read | ✓ | ✗ | ✓ | Hidden evaluation labels never returned |
| `get_job(job_id)` | Read | ✓ | ✗ | ✓ | |
| `get_client_history(client_id)` | Read | ✓ | ✗ | ✓ | Payment verified, spent, hires, rating |
| `get_connects_balance()` | Read | ✓ | ✗ | ✓ | |
| `get_price_stats(skill)` | Read | ✓ | ✗ | ✓ | p25 / median / p75 from real Kaggle data |
| `list_messages(client_id?)` | Read | ✓ | ✗ | ✓ | |
| `list_proposals()` | Read | ✓ | ✗ | ✓ | Status per proposal (submitted / ignored / replied / interview / hired); feeds outcome memory and the pipeline |
| `create_proposal_draft(job_id, cover_letter, bid_amount, idempotency_key, screening_answers)` | Write (local) | ✗ | ✗ | ✓ | Nothing is sent; same key = same draft |
| `submit_proposal(draft_id, idempotency_key, dry_run=True)` | Write | ✗ | ✓ | ✓ | **Spends Connects.** Dry run by default; only after human approval |
| `send_message(client_id, text, idempotency_key, job_id?, dry_run=True)` | Write | ✗ | ✗ | ✓ | Dry run by default; only after human approval |

Errors the agents/UI can rely on: `marketplace_unavailable` (degraded mode), `not_found`, `rate_limited`, `not_enough_connects`.

## Portfolio server (`mcp_servers/portfolio`), written by us

Read-only. Persona chosen by `PORTFOLIO_PERSONA`; retriever chosen by `RAG_VARIANT`. Auth: stdio (local, single user).

| Tool | Read / Write | readOnly | destructive | idempotent | Notes |
|---|---|---|---|---|---|
| `search_evidence(requirement, k, types?, outcomes?, since?)` | Read | ✓ | ✗ | ✓ | Returns evidence with type, source, date, outcome, score |
| `get_case_study(evidence_id)` | Read | ✓ | ✗ | ✓ | Full text of any evidence item |
| `list_skills()` | Read | ✓ | ✗ | ✓ | Skills with evidence counts |

Resources: `portfolio://case/{case_id}`, `portfolio://proposal/{proposal_id}`, `portfolio://profile`.
Prompts: `answer_screening_question(question)`, `best_proof_for_job(job_description)`.

## Workspace server (`mcp_servers/workspace`), written by us

Local mock (a JSON file, `WORKSPACE_DATA`), not Google Calendar / Gmail: nothing leaves the machine. Swapping in the
official Google APIs changes only this server; agents see the same MCP tools. Auth: stdio (local, single user).

| Tool | Read / Write | readOnly | destructive | idempotent | Notes |
|---|---|---|---|---|---|
| `free_slots(days_ahead, duration_min, limit)` | Read | ✓ | ✗ | ✓ | Weekdays, working hours (`WORKSPACE_HOURS`), one slot per day, skips existing holds |
| `create_hold(start, title, idempotency_key, duration_min)` | Write (local) | ✗ | ✗ | ✓ | **Tentative** interview hold; only after the user approves the reply; same key = same hold |
| `list_holds()` | Read | ✓ | ✗ | ✓ | |
| `create_email_draft(to, subject, body, idempotency_key)` | Write (local) | ✗ | ✗ | ✓ | Saved as a draft, never sent |

## Which agent may call which tool (least privilege, `agent/config.yaml` → `tool_allowlist`)

Writes are split from reads: `liaison` (read + calendar slots) never sends; only `liaison_send` and `submit`
can write, and the graph reaches them only after `interrupt()` returns "approve".

## Third-party servers

| Server | Why we trust it |
|---|---|
| Upwork official MCP (`https://mcp.upwork.com/mcp`) | _TODO: one line_ |
| GitHub MCP | _TODO: one line_ |
