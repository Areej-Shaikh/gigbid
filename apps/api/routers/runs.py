from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from apps.api.auth.security import User
from apps.api.schemas.models import ResumeIn, RunList, RunState, RunSummary, Started

router = APIRouter(prefix="/runs", tags=["runs"])

KEEP = ("job", "client", "job_spec", "risk", "fit", "decision", "price", "draft", "verification", "critique",
        "compliance", "preview", "approval", "submission", "status", "errors", "trace", "tokens", "evidence", "edits")


@router.get("", response_model=RunList)
def list_runs(request: Request, user: str = User):
    rows = sorted(request.app.state.runs.index.data.values(), key=lambda r: r.get("updated", ""), reverse=True)
    return RunList(runs=[RunSummary(**{"title": "", "status": "unknown", **r}) for r in rows])


@router.post("/{job_id}", response_model=Started)
async def start_run(job_id: str, request: Request, user: str = User):
    started = request.app.state.runs.start(job_id, user=user)
    return Started(job_id=job_id, started=started, message="started" if started else "already running")


@router.get("/{job_id}", response_model=RunState)
async def get_run(job_id: str, request: Request, user: str = User):
    m = request.app.state.runs
    s = await m.graph.aget_state(m.conf(job_id))
    if not s.values:
        raise HTTPException(404, "this job has not been analysed yet")
    interrupt = s.tasks[0].interrupts[0].value if s.tasks and s.tasks[0].interrupts else None
    return RunState(job_id=job_id, status=s.values.get("status", "unknown"), running=m.running(job_id),
                    next=list(s.next), interrupt=interrupt, values={k: s.values.get(k) for k in KEEP})


@router.post("/{job_id}/resume", response_model=Started)
async def resume_run(job_id: str, body: ResumeIn, request: Request, user: str = User):
    m = request.app.state.runs
    s = await m.graph.aget_state(m.conf(job_id))
    if not (s.tasks and s.tasks[0].interrupts):
        raise HTTPException(409, "this run is not waiting for approval")
    started = m.start(job_id, resume=body.model_dump(exclude_none=True), user=user)
    return Started(job_id=job_id, started=started, message=body.action)


@router.get("/{job_id}/events")
async def run_events(job_id: str, request: Request, user: str = User):
    """Server-Sent Events: start, node (one per finished node), interrupt, error, done."""
    return EventSourceResponse(request.app.state.runs.subscribe(job_id))
