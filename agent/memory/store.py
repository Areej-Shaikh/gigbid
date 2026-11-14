"""Long-term memory store (R7, C2): a LangGraph BaseStore, kept apart from graph state and the trace.

Namespaces (all per user, so one freelancer never sees another's memory):
  ("style", user)              promoted style rules        <- what the Writer and Critic use
  ("style_candidates", user)   edit patterns seen so far   <- waiting for the promotion rule
  ("outcome", user)            promoted category stats      <- what the Writer uses
  ("outcome_events", user)     one label per job outcome    <- input to the promotion rule

Only agent/memory/promotion_rules.py writes to "style" and "outcome".
"""
from contextlib import asynccontextmanager
from pathlib import Path

from langgraph.store.base import BaseStore

STYLE, STYLE_CANDIDATES, OUTCOME, OUTCOME_EVENTS = "style", "style_candidates", "outcome", "outcome_events"
VIEWABLE = (STYLE, OUTCOME, STYLE_CANDIDATES)      # what the Settings screen shows (and can delete)


def ns(kind: str, user: str) -> tuple[str, str]:
    return (kind, user or "default")


@asynccontextmanager
async def open_store(path: str | Path = "data/processed/memory.sqlite"):
    """Persistent store for the API (survives restarts). Tests use InMemoryStore instead."""
    from langgraph.store.sqlite.aio import AsyncSqliteStore
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteStore.from_conn_string(str(path)) as store:
        await store.setup()
        yield store


def current_store() -> BaseStore | None:
    """The store the running graph was compiled with, or None (e.g. evals compiled without memory)."""
    try:
        from langgraph.config import get_store
        return get_store()
    except Exception:  # noqa: BLE001 - outside a graph run, or no store configured
        return None


def user_of(config) -> str:
    return ((config or {}).get("configurable") or {}).get("user_id") or "default"


async def list_memory(store: BaseStore, user: str) -> dict[str, list[dict]]:
    out = {}
    for kind in VIEWABLE:
        items = await store.asearch(ns(kind, user), limit=200)
        out[kind] = [{"key": i.key, **i.value, "updated_at": i.updated_at.isoformat()} for i in items]
    return out


async def delete_memory(store: BaseStore, user: str, kind: str, key: str) -> bool:
    if kind not in VIEWABLE or await store.aget(ns(kind, user), key) is None:
        return False
    await store.adelete(ns(kind, user), key)
    return True
