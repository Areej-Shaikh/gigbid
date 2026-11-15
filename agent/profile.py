"""Per-user profile from onboarding (D: sign-in and onboarding): persona, rates, weekly Connects budget, saved searches.

Stored in the LangGraph store under ("profile", user), the same store as long-term memory (Postgres in production),
so it is tenant-scoped like everything else. Agents read it at run time:
  - the persona selects whose portfolio the Portfolio MCP server searches (sent in the MCP request _meta),
  - the rates set the price floor, and the weekly budget caps how many Connects one bid may cost.
Missing fields fall back to config.yaml -> user and the server's default persona.
"""
import os
from contextvars import ContextVar
from pathlib import Path

from agent.config import cfg

NS = ("profile",)
KEY = "settings"
PERSONAS_DIR = Path("data/personas")

# the persona for the current run; ToolBox.call forwards it to the Portfolio server in the MCP request _meta
current_persona: ContextVar[str | None] = ContextVar("current_persona", default=None)


def personas() -> list[str]:
    return sorted(p.name for p in PERSONAS_DIR.iterdir() if p.is_dir() and (p / "profile.json").exists()) \
        if PERSONAS_DIR.exists() else []


def defaults(user: str) -> dict:
    u = cfg()["user"]
    return {"persona": os.getenv("PORTFOLIO_PERSONA", "ai_ml_engineer"), "min_hourly_rate": float(u["min_hourly_rate"]),
            "min_fixed_budget": float(u["min_fixed_budget"]), "weekly_connects_budget": int(u["weekly_connects_budget"]),
            "saved_searches": [s["query"] for s in cfg().get("scout", {}).get("saved_searches", []) if s.get("user") == user],
            "marketplace": os.getenv("MARKETPLACE_MODE", "gigsim"), "onboarded": False}


async def get_profile(store, user: str | None) -> dict:
    user = user or "default"
    base = defaults(user)
    if store is None:
        return base
    item = await store.aget((*NS, user), KEY)
    return {**base, **(item.value if item else {})}


async def save_profile(store, user: str, changes: dict) -> dict:
    current = await get_profile(store, user)
    if changes.get("persona") and changes["persona"] not in personas():
        raise ValueError(f"unknown persona {changes['persona']!r}")
    merged = {**current, **{k: v for k, v in changes.items() if v is not None}}
    await store.aput((*NS, user), KEY, merged)
    return merged
