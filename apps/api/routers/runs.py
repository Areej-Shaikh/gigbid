import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agent.config import cfg
from agent.llm import structured
from agent.nodes.common import CITE, fence, prompt, sentences
from agent.nodes.compliance import check
from agent.nodes.verifier import CLAIM, _lexical
from apps.api.auth.security import User
from apps.api.schemas.models import (
    Checkpoint,
    CheckpointHistory,
    RegenerateIn,
    RegenerateOut,
    ReplayIn,
    ResumeIn,
    RunList,
    RunState,
    RunSummary,
    Started,
)

router = APIRouter(prefix="/runs", tags=["runs"])

KEEP = ("job", "client", "job_spec", "risk", "fit", "decision", "price", "draft", "verification", "critique",
        "compliance", "preview", "approval", "submission", "status", "errors", "trace", "tokens", "evidence", "edits")


@router.get("", response_model=RunList)
def list_runs(request: Request, user: str = User):
    rows = sorted(request.app.state.runs.index.rows(user), key=lambda r: r.get("updated", ""), reverse=True)
    return RunList(runs=[RunSummary(**{"title": "", "status": "unknown", **r}) for r in rows])


@router.post("/{job_id}", response_model=Started)
async def start_run(job_id: str, request: Request, user: str = User):
    started = request.app.state.runs.start(job_id, user=user)
    return Started(job_id=job_id, started=started, message="started" if started else "already running")


@router.get("/{job_id}", response_model=RunState)
async def get_run(job_id: str, request: Request, user: str = User):
    m = request.app.state.runs
    s = await m.graph.aget_state(m.conf(job_id, user))
    if not s.values:
        raise HTTPException(404, "this job has not been analysed yet")
    interrupt = s.tasks[0].interrupts[0].value if s.tasks and s.tasks[0].interrupts else None
    row = m.index.row(job_id, user)
    return RunState(job_id=job_id, status=s.values.get("status", "unknown"), running=m.running(job_id, user),
                    next=list(s.next), interrupt=interrupt, values={k: s.values.get(k) for k in KEEP},
                    trace_id=row.get("trace_id"), trace_url=row.get("trace_url"))


@router.post("/{job_id}/resume", response_model=Started)
async def resume_run(job_id: str, body: ResumeIn, request: Request, user: str = User):
    m = request.app.state.runs
    s = await m.graph.aget_state(m.conf(job_id, user))
    if not (s.tasks and s.tasks[0].interrupts):
        raise HTTPException(409, "this run is not waiting for approval")
    started = m.start(job_id, resume=body.model_dump(exclude_none=True), user=user)
    return Started(job_id=job_id, started=started, message=body.action)


@router.get("/{job_id}/events")
async def run_events(job_id: str, request: Request, user: str = User):
    """Server-Sent Events: start, node (one per finished node), interrupt, error, done."""
    return EventSourceResponse(request.app.state.runs.subscribe(job_id, user))


@router.get("/{job_id}/history", response_model=CheckpointHistory)
async def run_history(job_id: str, request: Request, user: str = User):
    """Every checkpoint of this job's thread (newest first): what ran, and what would run next on replay."""
    m = request.app.state.runs
    snaps = [s async for s in m.graph.aget_state_history(m.conf(job_id, user))]          # newest first
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
                async for s in m.graph.aget_state_history(m.conf(job_id, user))]):
        raise HTTPException(404, "no such checkpoint for this job")
    started = m.start(job_id, user=user, replay_from=body.checkpoint_id)
    return Started(job_id=job_id, started=started, message="replaying" if started else "already running")


class _Paragraph(BaseModel):
    paragraph: str


def _rule_paragraph(paragraph: str, evidence: dict) -> _Paragraph:
    """No LLM available: replace the paragraph with a claim built from evidence it does not cite yet."""
    used = set(CITE.findall(paragraph))
    for eid, e in evidence.items():
        if eid not in used and e.get("text"):
            first = re.split(r"(?<=[.!?])\s+", e["text"].strip())
            result = next((s for s in first if re.search(r"\d", s)), first[0])[:220].rstrip(".")
            return _Paragraph(paragraph=f"I have done similar work: {e.get('title', eid)}. {result} [{eid}].")
    return _Paragraph(paragraph=paragraph)


@router.post("/{job_id}/regenerate", response_model=RegenerateOut)
async def regenerate_paragraph(job_id: str, body: RegenerateIn, request: Request, user: str = User):
    """Proposal studio: rewrite ONE paragraph of the draft waiting for approval, from the same evidence. The result is
    checked like a fresh draft (unsupported claims dropped, Compliance rules applied) and returned as a suggestion; the
    user accepts it through the normal Edit path, which re-runs Compliance and feeds style memory."""
    m = request.app.state.runs
    s = await m.graph.aget_state(m.conf(job_id, user))
    if not (s.tasks and s.tasks[0].interrupts):
        raise HTTPException(409, "this run is not waiting for approval")
    v = s.values
    evidence = v.get("evidence") or {}
    evidence_lines = "\n".join(f"[{k}] {e.get('title', '')}: {(e.get('text') or e.get('snippet', ''))[:600]}"
                               for k, e in evidence.items())
    user_msg = "\n\n".join(filter(None, [
        fence(v.get("job") or {}),
        f"EVIDENCE (cite these ids only):\n{evidence_lines}",
        f"WHOLE PROPOSAL (for context):\n{(v.get('draft') or {}).get('cover_letter', '')}",
        f"PARAGRAPH TO REWRITE:\n{body.paragraph}",
        f"INSTRUCTION: {body.instruction}" if body.instruction else "",
    ]))
    res, info = await structured("writer", _Paragraph, prompt("regenerate"), user_msg, lambda: _rule_paragraph(body.paragraph, evidence))
    kept = []
    for sent in sentences(res.paragraph):          # same claim rule as the verifier: no uncited / unsupported claims
        ids = CITE.findall(sent)
        if (ids or CLAIM.search(sent)) and _lexical(sent, ids, evidence).status == "unsupported":
            continue
        kept.append(sent)
    text, violations = check(" ".join(kept), cfg()["compliance"]["rules"])
    if not text.strip():
        raise HTTPException(422, "the regenerated paragraph did not pass the claim and policy checks; edit it by hand")
    return RegenerateOut(paragraph=text, model=info["model"], removed_by_compliance=violations)
