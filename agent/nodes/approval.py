"""Human approval (C5): preview with dry_run, then interrupt() and wait for the human.
Nothing reaches the client until a human approves it."""
import difflib

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from agent.handoffs import ApprovalDecision
from agent.mcp_client import ToolCallError
from agent.nodes.common import CITE, thread_id, toolbox, trace


def _draft_key(state, config) -> str:
    return f"{thread_id(config)}-draft-v{len(state.get('edits') or [])}"


async def preview(state, config: RunnableConfig):
    """Create the draft on the marketplace and get the dry_run preview (what will be sent + cost)."""
    tb, d, price = toolbox(config), state["draft"], state["price"]
    draft = await tb.call("preview", "create_proposal_draft", job_id=state["job"]["job_id"],
                          cover_letter=d["cover_letter"], bid_amount=price["amount"],
                          screening_answers=d.get("screening_answers", []), idempotency_key=_draft_key(state, config))
    dry = await tb.call("preview", "submit_proposal", draft_id=draft["draft_id"],
                        idempotency_key=f"{thread_id(config)}-submit", dry_run=True)  # dry_run is forced here
    return {"preview": {"draft_id": draft["draft_id"], **dry}, "status": "awaiting_approval",
            "trace": [trace("preview", draft_id=draft["draft_id"], connects_cost=dry["connects_cost"])]}


async def human_approval(state, config: RunnableConfig):
    d = state["draft"]
    cited = sorted(set(CITE.findall(" ".join([d["cover_letter"]] + d.get("screening_answers", [])))))
    ev = state.get("evidence") or {}
    payload = {
        "job": {k: state["job"].get(k) for k in ("job_id", "title", "budget_type", "budget_min", "budget_max", "connects_cost")},
        "draft": d,
        "evidence": {i: {"title": ev.get(i, {}).get("title"), "snippet": ev.get(i, {}).get("snippet")} for i in cited},
        "fit_matrix": state["fit"]["matrix"],
        "risk": state["risk"],
        "price": state["price"],
        "verification": state.get("verification"),
        "critique": state.get("critique"),
        "compliance": state.get("compliance"),
        "dry_run": state.get("preview"),
    }
    decision = ApprovalDecision(**interrupt(payload))     # graph pauses here until the human answers
    out = {"approval": decision.model_dump(), "trace": [trace("human_approval", action=decision.action)]}
    if decision.action == "edit":
        new = {"cover_letter": decision.cover_letter or d["cover_letter"],
               "screening_answers": decision.screening_answers or d.get("screening_answers", [])}
        diff = list(difflib.unified_diff(d["cover_letter"].split(". "), new["cover_letter"].split(". "), lineterm="", n=0))
        out["draft"] = new
        out["edits"] = [{"before": d["cover_letter"], "after": new["cover_letter"], "diff": diff}]  # -> style memory
    elif decision.action == "reject":
        out["status"] = "rejected"
    return out


def route_after_approval(state) -> str:
    return {"approve": "submit", "edit": "compliance", "reject": "end"}[state["approval"]["action"]]


async def submit(state, config: RunnableConfig):
    """Runs only after approval. Idempotency keys come from the thread id, so a crash + resume
    re-sends the SAME request and the marketplace never submits twice or charges twice."""
    tb, d, price = toolbox(config), state["draft"], state["price"]
    try:
        draft = await tb.call("submit", "create_proposal_draft", job_id=state["job"]["job_id"],
                              cover_letter=d["cover_letter"], bid_amount=price["amount"],
                              screening_answers=d.get("screening_answers", []), idempotency_key=_draft_key(state, config))
        res = await tb.call("submit", "submit_proposal", draft_id=draft["draft_id"],
                            idempotency_key=f"{thread_id(config)}-submit", dry_run=False)
    except ToolCallError as e:
        if "marketplace_unavailable" in str(e):
            raise  # keep the thread paused at this node; resume later to retry (nothing lost)
        return {"status": "needs_attention", "errors": [f"submit: {e}"], "trace": [trace("submit", error=str(e))]}
    return {"submission": res, "status": "submitted",
            "trace": [trace("submit", proposal_id=res["proposal_id"], connects_spent=res["connects_cost"])]}
