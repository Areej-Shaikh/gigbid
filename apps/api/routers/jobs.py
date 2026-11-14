from fastapi import APIRouter, HTTPException, Request

from agent.mcp_client import ToolCallError
from apps.api.auth.security import User
from apps.api.schemas.models import JobCard, JobList

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobList)
async def list_jobs(request: Request, q: str = "", limit: int = 30, offset: int = 0, user: str = User):
    app = request.app.state
    try:
        res = await app.toolbox.call("api", "search_jobs", query=q, limit=limit, offset=offset)
    except ToolCallError as e:
        raise HTTPException(503, f"marketplace unavailable: {e}")
    cards = []
    for j in res["jobs"]:
        r = app.runs.index.data.get(j["job_id"], {})
        cards.append(JobCard(**{k: j.get(k) for k in JobCard.model_fields if k in j},
                             status=r.get("status"), action=r.get("action"), fit=r.get("fit"),
                             risk=r.get("risk"), risk_flags=r.get("risk_flags") or [], price=r.get("price")))
    # analysed jobs first, best fit first
    cards.sort(key=lambda c: (c.fit is None, -(c.fit or 0)))
    return JobList(jobs=cards)
