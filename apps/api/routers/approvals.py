"""Approvals (C5): resume a bid run paused at human approval with approve, edit or reject.
Client-message approvals live with their conversations (routers/conversations.py)."""
from fastapi import APIRouter, HTTPException, Request

from apps.api.auth.security import User
from apps.api.schemas.models import ResumeIn, Started

router = APIRouter(prefix="/runs", tags=["approvals"])


@router.post("/{job_id}/resume", response_model=Started)
async def resume_run(job_id: str, body: ResumeIn, request: Request, user: str = User):
    m = request.app.state.runs
    s = await m.graph.aget_state(m.conf(job_id, user))
    if not (s.tasks and s.tasks[0].interrupts):
        raise HTTPException(409, "this run is not waiting for approval")
    started = m.start(job_id, resume=body.model_dump(exclude_none=True), user=user)
    return Started(job_id=job_id, started=started, message=body.action)
