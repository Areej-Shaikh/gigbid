"""Client conversations: list threads, run the Client Liaison, approve / edit / reject its reply."""
from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from apps.api.auth.security import User
from apps.api.schemas.models import (ConversationList, ConversationState, ConversationSummary, Message,
                                     MessageResumeIn, Started)

router = APIRouter(prefix="/conversations", tags=["conversations"])
KEEP = ("client_id", "job_id", "job", "incoming", "intent", "slots", "draft", "compliance", "preview",
        "approval", "sent", "status", "errors", "trace", "tokens", "edits")


async def _messages(request: Request, client_id: str | None = None) -> list[dict]:
    args = {"client_id": client_id} if client_id else {}
    return (await request.app.state.toolbox.call("api", "list_messages", **args))["messages"]


@router.get("", response_model=ConversationList)
async def list_conversations(request: Request, user: str = User):
    by_client: dict[str, list[dict]] = {}
    for m in sorted(await _messages(request), key=lambda m: m["sent_at"]):
        by_client.setdefault(m["client_id"], []).append(m)
    idx = request.app.state.convs.index.data
    out = []
    for cid, ms in by_client.items():
        last_mine = max((i for i, m in enumerate(ms) if m["sender"] == "freelancer"), default=-1)
        row = idx.get(cid, {})
        out.append(ConversationSummary(
            client_id=cid, job_id=next((m["job_id"] for m in reversed(ms) if m.get("job_id")), None),
            last_text=ms[-1]["text"][:160], last_sender=ms[-1]["sender"], last_at=ms[-1]["sent_at"],
            unanswered=sum(m["sender"] == "client" for m in ms[last_mine + 1:]),
            status=row.get("status"), intent=row.get("intent")))
    out.sort(key=lambda c: c.last_at, reverse=True)       # newest first...
    out.sort(key=lambda c: c.unanswered == 0)             # ...but threads waiting for a reply on top (stable sort)
    return ConversationList(conversations=out)


@router.post("/{client_id}/run", response_model=Started)
async def run_liaison(client_id: str, request: Request, user: str = User):
    """Ask the Client Liaison to read new messages and draft a reply (paused for approval)."""
    m = request.app.state.convs
    s = await m.graph.aget_state(m.conf(client_id, user))
    if s.next:                                  # already waiting for approval (or mid-run): don't start over
        return Started(job_id=client_id, started=m.start(client_id, user=user), message="continuing")
    started = m.start(client_id, user=user, restart=True)
    return Started(job_id=client_id, started=started, message="started" if started else "already running")


@router.get("/{client_id}", response_model=ConversationState)
async def get_conversation(client_id: str, request: Request, user: str = User):
    m = request.app.state.convs
    s = await m.graph.aget_state(m.conf(client_id, user))
    interrupt = s.tasks[0].interrupts[0].value if s.tasks and s.tasks[0].interrupts else None
    msgs = sorted(await _messages(request, client_id), key=lambda x: x["sent_at"])
    if not msgs and not s.values:
        raise HTTPException(404, "no conversation with this client")
    return ConversationState(client_id=client_id, status=(s.values or {}).get("status", "new"),
                             running=m.running(client_id), next=list(s.next), interrupt=interrupt,
                             messages=[Message(**x) for x in msgs],
                             values={k: (s.values or {}).get(k) for k in KEEP})


@router.post("/{client_id}/resume", response_model=Started)
async def resume_liaison(client_id: str, body: MessageResumeIn, request: Request, user: str = User):
    m = request.app.state.convs
    s = await m.graph.aget_state(m.conf(client_id, user))
    if not (s.tasks and s.tasks[0].interrupts):
        raise HTTPException(409, "this conversation is not waiting for approval")
    if body.action == "reject" and not (body.reason or "").strip():
        raise HTTPException(422, "a reason is required to reject")
    started = m.start(client_id, resume=body.model_dump(exclude_none=True), user=user)
    return Started(job_id=client_id, started=started, message=body.action)


@router.get("/{client_id}/events")
async def conversation_events(client_id: str, request: Request, user: str = User):
    """Server-Sent Events: start, node, interrupt, error, done."""
    return EventSourceResponse(request.app.state.convs.subscribe(client_id))
