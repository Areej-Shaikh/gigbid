"""Outcome sync: read proposal statuses from the marketplace (MCP, read-only) and pass each known
outcome through the promotion rule. Safe to run any number of times: one event per job, overwritten."""
import re

from langgraph.store.base import BaseStore

from agent.mcp_client import ToolBox
from agent.memory.promotion_rules import record_outcome

CITE = re.compile(r"\[([A-Za-z0-9_\-]+)\]")
KNOWN = {"ignored", "replied", "interview", "hired"}    # "submitted" = no outcome yet


async def sync_outcomes(tb: ToolBox, store: BaseStore, user: str) -> dict:
    props = (await tb.call("outcomes", "list_proposals"))["proposals"]
    recorded, promoted = 0, []
    for p in props:
        if p["status"] not in KNOWN:
            continue
        job = await tb.call("outcomes", "get_job", job_id=p["job_id"])
        stats = await record_outcome(store, user, job, p["status"], sorted(set(CITE.findall(p["cover_letter"]))))
        recorded += 1
        if stats:
            promoted.append(stats["category"])
    return {"proposals": len(props), "outcomes_recorded": recorded, "categories_promoted": sorted(set(promoted))}
