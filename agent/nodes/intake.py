"""Intake: load the job and its client from the marketplace (start of the bid graph)."""
from langchain_core.runnables import RunnableConfig

from agent.mcp_client import ToolCallError
from agent.nodes.common import toolbox, trace


async def intake(state, config: RunnableConfig):
    tb = toolbox(config)
    try:
        job = await tb.call("intake", "get_job", job_id=state["job_id"])
        client = await tb.call("intake", "get_client_history", client_id=job["client_id"])
    except ToolCallError as e:
        status = "marketplace_unavailable" if "marketplace_unavailable" in str(e) else "dead_letter"
        return {"status": status, "errors": [f"intake: {e}"], "trace": [trace("intake", error=str(e))]}
    return {"job": job, "client": client, "status": "running", "revisions": 0,
            "trace": [trace("intake", tools=["get_job", "get_client_history"], title=job["title"])]}
