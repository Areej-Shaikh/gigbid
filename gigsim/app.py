"""Mock GigSim: a small fake freelance marketplace for safe local testing."""
import json
import random
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
DB_FILE = ROOT / "data" / "processed" / "gigsim_db.json"      # built by scripts/prepare_data.py
STATS_FILE = ROOT / "data" / "processed" / "price_stats.json"
if DB_FILE.exists():
    SEED = json.loads(DB_FILE.read_text(encoding="utf-8"))
else:  # fallback: tiny hand-made seed
    SEED = json.loads((Path(__file__).parent / "seed.json").read_text(encoding="utf-8"))
PRICE_STATS = json.loads(STATS_FILE.read_text(encoding="utf-8")) if STATS_FILE.exists() else {}
HIDDEN = {"labels", "source", "dataset"}  # answer keys for evaluation: agents must never see them


def public(job: dict) -> dict:
    return {k: v for k, v in job.items() if k not in HIDDEN}

app = FastAPI(title="GigSim (mock marketplace)")

# In-memory state, reset on restart
state = {
    "connects": SEED["freelancer"]["connects_balance"],
    "proposals": {},     # proposal_id -> proposal
    "idempotency": {},   # idempotency key -> proposal_id
    "messages": list(SEED["messages"]),
}
JOBS = {j["job_id"]: j for j in SEED["jobs"]}
CLIENTS = {c["client_id"]: c for c in SEED["clients"]}

# ---- simple rate limit (30 requests per minute) + occasional errors ----
RATE_LIMIT = 30
calls: list[float] = []
ERROR_RATE = 0.05  # 5% random 503s, so you test retries


@app.middleware("http")
async def limits(request: Request, call_next):
    if request.url.path in ("/health", "/docs", "/openapi.json"):
        return await call_next(request)
    now = time.time()
    calls[:] = [t for t in calls if now - t < 60]
    if len(calls) >= RATE_LIMIT:
        return JSONResponse({"error": "rate_limited"}, status_code=429, headers={"Retry-After": "10"})
    calls.append(now)
    if random.random() < ERROR_RATE:
        return JSONResponse({"error": "temporary_failure"}, status_code=503)
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------- READ ----------------
@app.get("/jobs")
def search_jobs(q: str = "", limit: int = 20, offset: int = 0):
    q = q.lower()
    hits = [j for j in JOBS.values()
            if not q or q in j["title"].lower() or q in j["description"].lower()
            or any(q in s.lower() for s in j["skills"])]
    return [public(j) for j in hits[offset:offset + limit]]


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "job not found")
    return public(JOBS[job_id])


@app.get("/clients/{client_id}")
def get_client(client_id: str):
    if client_id not in CLIENTS:
        raise HTTPException(404, "client not found")
    return {k: v for k, v in CLIENTS[client_id].items() if k != "source"}


@app.get("/stats/prices")
def price_stats(skill: str):
    """Market price percentiles for a skill (from real Kaggle data)."""
    for k, v in PRICE_STATS.items():
        if k.lower() == skill.lower():
            return {"skill": k, **v}
    raise HTTPException(404, "no price data for this skill")


@app.get("/connects")
def get_connects():
    return {"balance": state["connects"]}


@app.get("/messages")
def list_messages(client_id: str | None = None):
    return [m for m in state["messages"] if not client_id or m["client_id"] == client_id]


@app.get("/proposals")
def list_proposals():
    return list(state["proposals"].values())


# ---------------- WRITE ----------------
class ProposalIn(BaseModel):
    job_id: str
    cover_letter: str
    bid_amount: float
    screening_answers: list[str] = []


@app.post("/proposals")
def submit_proposal(p: ProposalIn, idempotency_key: str = Header(...)):
    # Same key again -> return the same proposal, never charge twice
    if idempotency_key in state["idempotency"]:
        return state["proposals"][state["idempotency"][idempotency_key]]
    job = JOBS.get(p.job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if state["connects"] < job["connects_cost"]:
        raise HTTPException(402, "not enough connects")
    state["connects"] -= job["connects_cost"]
    pid = f"prop-{uuid.uuid4().hex[:8]}"
    proposal = {"proposal_id": pid, **p.model_dump(), "status": "submitted",
                "connects_spent": job["connects_cost"]}
    state["proposals"][pid] = proposal
    state["idempotency"][idempotency_key] = pid
    return proposal


class MessageIn(BaseModel):
    client_id: str
    job_id: str | None = None
    text: str


@app.post("/messages")
def send_message(m: MessageIn, idempotency_key: str = Header(...)):
    for msg in state["messages"]:
        if msg.get("idempotency_key") == idempotency_key:
            return msg
    msg = {"message_id": f"msg-{uuid.uuid4().hex[:8]}", **m.model_dump(),
           "sender": "freelancer", "sent_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "idempotency_key": idempotency_key}
    state["messages"].append(msg)
    return msg
