import statistics
from collections import Counter

from fastapi import APIRouter, Request

from agent.config import cfg
from agent.mcp_client import ToolCallError
from apps.api.auth.security import User
from apps.api.schemas.models import Analytics, Message, MessageList, Settings

router = APIRouter(tags=["analytics"])


@router.get("/analytics", response_model=Analytics)
def analytics(request: Request, user: str = User):
    rows = list(request.app.state.runs.index.data.values())
    lat = sorted(r["duration_s"] for r in rows if r.get("duration_s"))
    q = statistics.quantiles(lat, n=20) if len(lat) >= 2 else None
    return Analytics(
        analysed=len(rows),
        by_status=dict(Counter(r.get("status", "unknown") for r in rows)),
        by_action=dict(Counter(r.get("action") or "none" for r in rows)),
        submitted=sum(r.get("status") == "submitted" for r in rows),
        connects_spent=sum(r.get("connects_spent") or 0 for r in rows),
        avg_tokens_per_job=round(statistics.mean([r.get("tokens") or 0 for r in rows]), 1) if rows else 0,
        p50_latency_s=statistics.median(lat) if lat else None,
        p95_latency_s=round(q[18], 2) if q else (lat[0] if lat else None),
        top_reject_reasons=[r for r, _ in Counter(r["reject_reason"] for r in rows if r.get("reject_reason")).most_common(5)],
        top_skip_reasons=[r for r, _ in Counter(x.split(":")[0] for r in rows if r.get("action") == "skip"
                                                for x in r.get("skip_reasons") or []).most_common(5)])


@router.get("/messages", response_model=MessageList)
async def messages(request: Request, user: str = User):
    res = await request.app.state.toolbox.call("api", "list_messages")
    return MessageList(messages=[Message(**m) for m in res["messages"]])


@router.get("/settings", response_model=Settings)
async def settings(request: Request, user: str = User):
    c = cfg()
    skills = await request.app.state.toolbox.call("api", "list_skills")
    p = c["profiles"][c["profile"]]
    return Settings(username=user, persona=skills["persona"], headline=skills["headline"],
                    hourly_rate=skills["hourly_rate"], skills=[s["skill"] for s in skills["skills"]],
                    llm_profile=c["profile"], models={n: p.get("models", {}).get(size, "rules") for n, size in c["nodes"].items()},
                    user=c["user"], decision=c["decision"], budgets=c["budgets"])
