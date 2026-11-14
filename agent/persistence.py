"""Where durable state lives (C6): the LangGraph checkpointer (paused / crashed threads) and the
long-term memory store (R7). Chosen by config, never hard-coded in the API or scripts.

  DATABASE_URL set   -> Postgres (docker compose, Render): survives restarts and redeploys
  DATABASE_URL unset -> SQLite files in data/processed/ (quick local development)

Windows note: psycopg's async driver cannot run on Windows' default (Proactor) event loop, which the MCP
stdio subprocesses need. So on Windows use SQLite locally, or run the API in Docker (Linux) with Postgres.
"""
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

CHECKPOINTS = Path("data/processed/checkpoints.sqlite")
MEMORY = Path("data/processed/memory.sqlite")


def backend() -> str:
    return "postgres" if os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://")) else "sqlite"


def _pg_url() -> str:
    url = os.environ["DATABASE_URL"]
    return "postgresql://" + url.removeprefix("postgres://") if url.startswith("postgres://") else url


@asynccontextmanager
async def open_persistence():
    """Yields (checkpointer, store). Both create their tables on first use (setup())."""
    if backend() == "postgres":
        if sys.platform == "win32":
            raise RuntimeError("Postgres persistence needs a Linux event loop: run the API in Docker, "
                               "or unset DATABASE_URL to use SQLite on Windows.")
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from langgraph.store.postgres.aio import AsyncPostgresStore
        async with AsyncPostgresSaver.from_conn_string(_pg_url()) as saver, \
                AsyncPostgresStore.from_conn_string(_pg_url()) as store:
            await saver.setup()
            await store.setup()
            yield saver, store
        return
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    from agent.memory.store import open_store
    CHECKPOINTS.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(CHECKPOINTS)) as saver, open_store(MEMORY) as store:
        yield saver, store
