# ADR 0005: Postgres checkpoints + idempotency keys for exactly-once writes

**Status:** accepted

## Context
Approvals can wait hours. The server can restart in between, or crash between a write and its checkpoint.

## Decision
LangGraph checkpointer and store in Postgres when `DATABASE_URL` is set (SQLite for local Windows dev,
where async psycopg cannot use the default event loop). Every write tool takes an idempotency key derived
from the thread id, and the marketplace returns the original result for a repeated key.

## Consequences
+ Pending approvals survive restarts; a resumed or replayed run never submits or sends twice
  (tested by killing the API mid-run: one proposal, Connects charged once).
− Requires a database in production (free Render Postgres in `render.yaml`).
