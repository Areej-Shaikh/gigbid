"""Marketplace MCP server (Part A2): wraps the marketplace port as MCP tools.

Agents NEVER call GigSim directly; they only see these tools.

Run:
  python -m mcp_servers.marketplace.server            # stdio (Claude Desktop, MCP Inspector)
  python -m mcp_servers.marketplace.server --http     # Streamable HTTP on :8002, bearer-token auth
"""
import contextvars
import functools
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from agent.marketplace_port import MarketplacePort, MarketplaceUnavailable, NotFound, get_marketplace

mcp = FastMCP("gigbid-marketplace")

# ---------------------------------------------------------------- plumbing
current_user = contextvars.ContextVar("current_user", default="local")
current_trace = contextvars.ContextVar("current_trace", default=None)

AUDIT_LOG = Path(os.getenv("AUDIT_LOG", "logs/audit.jsonl"))
RATE_LIMIT_PER_MIN = int(os.getenv("MARKETPLACE_RATE_LIMIT", "50"))  # stays under GigSim's 60/min
_calls: dict[str, list[float]] = {}
_drafts: dict[str, dict] = {}            # draft_id -> draft (TODO: move to Postgres)
_draft_keys: dict[str, str] = {}         # idempotency key -> draft_id

_market: MarketplacePort | None = None


def market() -> MarketplacePort:
    global _market
    if _market is None:
        _market = get_marketplace()
    return _market


def set_marketplace(m: MarketplacePort) -> None:
    """Used by tests to plug in a different adapter."""
    global _market
    _market = m


def _mask(text: str) -> str:
    """Hide emails and phone numbers in logs (R9)."""
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[email]", text)
    return re.sub(r"\+?\d[\d\s().-]{7,}\d", "[phone]", text)


def _audit(tool: str, args: dict, result: Any, error: str | None = None) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "user": current_user.get(),
             "trace_id": current_trace.get() or str(uuid.uuid4()), "tool": tool,
             "args": json.loads(_mask(json.dumps(args, default=str))),
             "result": _mask(json.dumps(result, default=str))[:500] if result is not None else None,
             "error": error}
    with AUDIT_LOG.open("a", encoding="utf-8") as f:  # append-only
        f.write(json.dumps(entry) + "\n")


def _check_rate_limit() -> None:
    user, now = current_user.get(), time.time()
    window = [t for t in _calls.get(user, []) if now - t < 60]
    if len(window) >= RATE_LIMIT_PER_MIN:
        raise ToolError("rate_limited: too many marketplace calls this minute, try again shortly")
    _calls[user] = window + [now]


def guarded(fn):
    """Rate limit + error mapping + audit log around every tool."""
    @functools.wraps(fn)
    async def wrapper(**kwargs):
        _check_rate_limit()
        try:
            result = await fn(**kwargs)
        except MarketplaceUnavailable as e:
            _audit(fn.__name__, kwargs, None, str(e))
            raise ToolError(f"marketplace_unavailable: {e}")
        except NotFound as e:
            _audit(fn.__name__, kwargs, None, str(e))
            raise ToolError(f"not_found: {e}")
        _audit(fn.__name__, kwargs, result.model_dump() if isinstance(result, BaseModel) else result)
        return result
    return wrapper


READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)

# ---------------------------------------------------------------- output models
class Job(BaseModel):
    job_id: str
    client_id: str
    title: str
    description: str = ""
    skills: list[str] = []
    budget_type: str
    budget_min: float | None = None
    budget_max: float | None = None
    connects_cost: int
    screening_questions: list[str] = []
    posted_at: str = ""
    country: str = ""
    experience_level: str = ""


class JobList(BaseModel):
    jobs: list[Job]
    count: int


class ClientHistory(BaseModel):
    client_id: str
    payment_verified: bool
    total_spent: float = 0
    hires: int = 0
    avg_rating: float | None = None
    reviews: int = 0
    country: str = ""
    industry: str = ""


class ConnectsBalance(BaseModel):
    balance: int


class PriceStats(BaseModel):
    skill: str
    found: bool
    hourly: dict[str, float] | None = None
    fixed: dict[str, float] | None = None


class Message(BaseModel):
    message_id: str
    client_id: str
    job_id: str | None = None
    sender: str
    text: str
    sent_at: str


class MessageList(BaseModel):
    messages: list[Message]


class ProposalStatus(BaseModel):
    proposal_id: str
    job_id: str
    client_id: str | None = None
    status: str = Field(description="submitted | ignored | replied | interview | hired")
    bid_amount: float
    cover_letter: str
    connects_spent: int = 0


class ProposalList(BaseModel):
    proposals: list[ProposalStatus]


class ProposalDraft(BaseModel):
    draft_id: str
    job_id: str
    cover_letter: str
    bid_amount: float
    screening_answers: list[str]
    connects_cost: int
    status: str = "draft"


class SubmitResult(BaseModel):
    dry_run: bool
    would_send: dict | None = None      # exactly what will be sent (dry run preview)
    connects_cost: int
    connects_balance_after: int
    proposal_id: str | None = None
    status: str


class SendResult(BaseModel):
    dry_run: bool
    would_send: dict | None = None
    message_id: str | None = None
    status: str


# ---------------------------------------------------------------- READ tools
@mcp.tool(annotations=READ)
@guarded
async def search_jobs(
    query: Annotated[str, Field(description="Keywords, e.g. 'python rag'. Empty = newest jobs.", max_length=200)] = "",
    limit: Annotated[int, Field(ge=1, le=50)] = 20,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> JobList:
    """Search open jobs on the marketplace by keyword (title, description or skill)."""
    jobs = [Job(**j) for j in await market().search_jobs(query, limit, offset)]
    return JobList(jobs=jobs, count=len(jobs))


@mcp.tool(annotations=READ)
@guarded
async def get_job(job_id: Annotated[str, Field(min_length=1, max_length=50)]) -> Job:
    """Get full details of one job: description, budget, skills, screening questions, Connects cost."""
    return Job(**await market().get_job(job_id))


@mcp.tool(annotations=READ)
@guarded
async def get_client_history(client_id: Annotated[str, Field(min_length=1, max_length=50)]) -> ClientHistory:
    """Get a client's track record: payment verified, total spent, hires, rating, reviews."""
    return ClientHistory(**await market().get_client(client_id))


@mcp.tool(annotations=READ)
@guarded
async def get_connects_balance() -> ConnectsBalance:
    """Get how many Connects the freelancer has left."""
    return ConnectsBalance(balance=await market().get_connects_balance())


@mcp.tool(annotations=READ)
@guarded
async def get_price_stats(skill: Annotated[str, Field(min_length=1, max_length=100)]) -> PriceStats:
    """Market price percentiles (p25, median, p75) for a skill, for hourly and fixed jobs."""
    s = await market().get_price_stats(skill)
    if not s:
        return PriceStats(skill=skill, found=False)
    return PriceStats(skill=s["skill"], found=True, hourly=s.get("hourly"), fixed=s.get("fixed"))


@mcp.tool(annotations=READ)
@guarded
async def list_messages(client_id: Annotated[str | None, Field(max_length=50)] = None) -> MessageList:
    """List conversation messages, optionally only for one client."""
    msgs = await market().list_messages(client_id)
    return MessageList(messages=[Message(**{k: m.get(k) for k in Message.model_fields if k in m}) for m in msgs])


@mcp.tool(annotations=READ)
@guarded
async def list_proposals() -> ProposalList:
    """List submitted proposals and their status (submitted, ignored, replied, interview, hired)."""
    props = await market().list_proposals()
    return ProposalList(proposals=[ProposalStatus(**{k: p.get(k) for k in ProposalStatus.model_fields if k in p})
                                   for p in props])


# ---------------------------------------------------------------- WRITE tools
@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True,
                                      openWorldHint=False))
@guarded
async def create_proposal_draft(
    job_id: Annotated[str, Field(min_length=1, max_length=50)],
    cover_letter: Annotated[str, Field(min_length=50, max_length=5000)],
    bid_amount: Annotated[float, Field(gt=0, le=100_000, description="USD; hourly rate or fixed price")],
    idempotency_key: Annotated[str, Field(min_length=8, max_length=100)],
    screening_answers: list[Annotated[str, Field(max_length=3000)]] = [],
) -> ProposalDraft:
    """Save a proposal as a DRAFT. Nothing is sent to the client. Same idempotency_key returns the same draft."""
    if idempotency_key in _draft_keys:
        return ProposalDraft(**_drafts[_draft_keys[idempotency_key]])
    job = await market().get_job(job_id)
    draft = ProposalDraft(draft_id=f"draft-{uuid.uuid4().hex[:8]}", job_id=job_id, cover_letter=cover_letter,
                          bid_amount=bid_amount, screening_answers=screening_answers,
                          connects_cost=job["connects_cost"])
    _drafts[draft.draft_id] = draft.model_dump()
    _draft_keys[idempotency_key] = draft.draft_id
    return draft


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True,
                                      openWorldHint=True))
@guarded
async def submit_proposal(
    draft_id: Annotated[str, Field(min_length=1, max_length=50)],
    idempotency_key: Annotated[str, Field(min_length=8, max_length=100)],
    dry_run: Annotated[bool, Field(description="True = only preview what would be sent and the cost")] = True,
) -> SubmitResult:
    """Submit an approved draft to the client. SPENDS CONNECTS. Only call after human approval.
    dry_run defaults to True; a retried call with the same idempotency_key never submits twice."""
    draft = _drafts.get(draft_id)
    if not draft:
        raise NotFound(f"draft {draft_id} not found")
    balance = await market().get_connects_balance()
    payload = {k: draft[k] for k in ("job_id", "cover_letter", "bid_amount", "screening_answers")}
    if dry_run:
        return SubmitResult(dry_run=True, would_send=payload, connects_cost=draft["connects_cost"],
                            connects_balance_after=balance - draft["connects_cost"], status="preview")
    if balance < draft["connects_cost"]:
        raise ToolError(f"not_enough_connects: need {draft['connects_cost']}, have {balance}")
    res = await market().submit_proposal(**payload, idempotency_key=idempotency_key)
    draft["status"] = "submitted"
    return SubmitResult(dry_run=False, connects_cost=draft["connects_cost"],
                        connects_balance_after=await market().get_connects_balance(),
                        proposal_id=res["proposal_id"], status=res["status"])


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True,
                                      openWorldHint=True))
@guarded
async def send_message(
    client_id: Annotated[str, Field(min_length=1, max_length=50)],
    text: Annotated[str, Field(min_length=1, max_length=5000)],
    idempotency_key: Annotated[str, Field(min_length=8, max_length=100)],
    job_id: Annotated[str | None, Field(max_length=50)] = None,
    dry_run: bool = True,
) -> SendResult:
    """Send a message to a client. Only call after human approval. dry_run defaults to True."""
    payload = {"client_id": client_id, "job_id": job_id, "text": text}
    if dry_run:
        return SendResult(dry_run=True, would_send=payload, status="preview")
    res = await market().send_message(**payload, idempotency_key=idempotency_key)
    return SendResult(dry_run=False, message_id=res["message_id"], status="sent")


# ---------------------------------------------------------------- HTTP + bearer auth
def http_app():
    """Streamable HTTP app with bearer-token auth.
    MARKETPLACE_MCP_TOKENS="token1:alice,token2:bob" maps tokens to users."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    tokens = dict(p.split(":", 1) for p in os.getenv("MARKETPLACE_MCP_TOKENS", "").split(",") if ":" in p)
    if not tokens:
        raise SystemExit("Set MARKETPLACE_MCP_TOKENS in .env, e.g. dev-token-123:demo")

    class BearerAuth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            auth = request.headers.get("authorization", "")
            user = tokens.get(auth.removeprefix("Bearer ").strip()) if auth.startswith("Bearer ") else None
            if not user:
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            u = current_user.set(user)
            t = current_trace.set(request.headers.get("x-trace-id"))
            try:
                return await call_next(request)
            finally:
                current_user.reset(u)
                current_trace.reset(t)

    app = mcp.streamable_http_app()
    app.add_middleware(BearerAuth)
    return app


if __name__ == "__main__":
    if "--http" in sys.argv:
        import uvicorn
        from dotenv import load_dotenv
        load_dotenv()
        uvicorn.run(http_app(), host="127.0.0.1", port=int(os.getenv("MARKETPLACE_MCP_PORT", "8002")))
    else:
        mcp.run()  # stdio
