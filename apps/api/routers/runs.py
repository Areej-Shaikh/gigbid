from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from apps.api.auth.security import User
from apps.api.schemas.models import Checkpoint, CheckpointHistory, ReplayIn, ResumeIn, RunList, RunState, RunSummary, Started

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


@router.get("/{job_id}/history", response_model=CheckpointHistory)
async def run_history(job_id: str, request: Request, user: str = User):
    """Every checkpoint of this job's thread (newest first): what ran, and what would run next on replay."""
    m = request.app.state.runs
    snaps = [s async for s in m.graph.aget_state_history(m.conf(job_id))]          # newest first
    out = [Checkpoint(checkpoint_id=s.config["configurable"]["checkpoint_id"], step=(s.metadata or {}).get("step", -1),
                      after=list(snaps[i + 1].next) if i + 1 < len(snaps) else ["__start__"],   # older one's "next" ran
                      next=list(s.next), status=(s.values or {}).get("status"), created_at=s.created_at)
           for i, s in enumerate(snaps)]
    if not out:
        raise HTTPException(404, "this job has not been analysed yet")
    return CheckpointHistory(job_id=job_id, checkpoints=out)


@router.post("/{job_id}/replay", response_model=Started)
async def replay_run(job_id: str, body: ReplayIn, request: Request, user: str = User):
    """Re-run the job from any earlier checkpoint (e.g. re-draft after changing a prompt). Safe: it still stops
    at human approval, and submit keeps the same idempotency key, so nothing is sent or charged twice."""
    m = request.app.state.runs
    if not any([s.config["configurable"]["checkpoint_id"] == body.checkpoint_id
                async for s in m.graph.aget_state_history(m.conf(job_id))]):
        raise HTTPException(404, "no such checkpoint for this job")
    started = m.start(job_id, user=user, replay_from=body.checkpoint_id)
    return Started(job_id=job_id, started=started, message="replaying" if started else "already running")
