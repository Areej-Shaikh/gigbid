# MCP Tools

All marketplace access goes through **one port** (`agent/marketplace_port.py`) with two adapters: `gigsim` (default) and `upwork` (live). Switch with `MARKETPLACE_MODE` in `.env`.

## Marketplace server (`mcp_servers/marketplace`), written by us

Auth: **stdio** = local user; **Streamable HTTP** (`--http`, port 8002) = bearer token (`MARKETPLACE_MCP_TOKENS`).
Every call: per-user rate limit (20/min, under GigSim's 30/min), append-only audit log `logs/audit.jsonl` (user, tool, args, result, trace id; emails and phones masked).

| Tool | Read / Write | readOnly | destructive | idempotent | Notes |
|---|---|---|---|---|---|
| `search_jobs(query, limit, offset)` | Read | ✓ | ✗ | ✓ | Hidden evaluation labels never returned |
| `get_job(job_id)` | Read | ✓ | ✗ | ✓ | |
| `get_client_history(client_id)` | Read | ✓ | ✗ | ✓ | Payment verified, spent, hires, rating |
| `get_connects_balance()` | Read | ✓ | ✗ | ✓ | |
| `get_price_stats(skill)` | Read | ✓ | ✗ | ✓ | p25 / median / p75 from real Kaggle data |
| `list_messages(client_id?)` | Read | ✓ | ✗ | ✓ | |
| `create_proposal_draft(job_id, cover_letter, bid_amount, idempotency_key, screening_answers)` | Write (local) | ✗ | ✗ | ✓ | Nothing is sent; same key = same draft |
| `submit_proposal(draft_id, idempotency_key, dry_run=True)` | Write | ✗ | ✓ | ✓ | **Spends Connects.** Dry run by default; only after human approval |
| `send_message(client_id, text, idempotency_key, job_id?, dry_run=True)` | Write | ✗ | ✗ | ✓ | Dry run by default; only after human approval |

Errors the agents/UI can rely on: `marketplace_unavailable` (degraded mode), `not_found`, `rate_limited`, `not_enough_connects`.

## Portfolio server (`mcp_servers/portfolio`), written by us
_TODO_

## Workspace server (`mcp_servers/workspace`), written by us
_TODO_

## Third-party servers

| Server | Why we trust it |
|---|---|
| Upwork official MCP (`https://mcp.upwork.com/mcp`) | _TODO: one line_ |
| GitHub MCP | _TODO: one line_ |
