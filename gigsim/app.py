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

# ---- simple rate limit (60 requests per minute) + occasional errors ----
RATE_LIMIT = 60
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
                "connects_spent": job["connects_cost"], "client_id": job.get("client_id")}
    state["proposals"][pid] = proposal
    state["idempotency"][idempotency_key] = pid
    client_reacts(proposal, job)
    return proposal


# ---------------- SIMULATED CLIENTS ----------------
# Each client decides whether to reply. Deterministic per (job, letter), so evaluations are repeatable.
# Hidden preferences: wants proof (evidence citations), wants its own skills mentioned, dislikes generic openings.
GENERIC = ("dear sir", "dear madam", "i am very passionate", "i have read your job post", "hardworking professional",
           "i am the best fit", "to whom it may concern")
REPLIES = {
    "question": "Thanks for the proposal. How would you approach {skill} for our project, and what would you deliver first?",
    "interview_request": "Your proposal stood out. Are you available for a short call this week to discuss {title}?",
    "negotiation": "Your experience looks right, but the rate is above our budget. Could you do it for ${counter}?",
}


def reply_probability(letter: str, job: dict) -> float:
    text = letter.lower()
    p = 0.15
    p += 0.30 if "[" in letter and "]" in letter else 0          # cites concrete evidence
    p += 0.25 if any(s.lower() in text for s in job.get("skills", [])) else 0
    p -= 0.25 if any(g in text[:160] for g in GENERIC) else 0
    return max(0.02, min(0.9, p))


def client_reacts(proposal: dict, job: dict) -> None:
    rng = random.Random(f"{job['job_id']}|{proposal['cover_letter']}")
    if rng.random() >= reply_probability(proposal["cover_letter"], job):
        proposal["status"] = "ignored"
        return
    intent = rng.choices(list(REPLIES), weights=[0.4, 0.35, 0.25])[0]
    proposal["status"] = "interview" if intent == "interview_request" else "replied"
    text = REPLIES[intent].format(skill=(job.get("skills") or ["this"])[0], title=job["title"][:60],
                                  counter=round(proposal["bid_amount"] * 0.8))
    state["messages"].append({"message_id": f"msg-{uuid.uuid4().hex[:8]}", "client_id": job.get("client_id"),
                              "job_id": job["job_id"], "sender": "client", "text": text,
                              "sent_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")})


class ClientMessageIn(BaseModel):
    client_id: str
    job_id: str | None = None
    text: str


@app.post("/dev/client_message")
def dev_client_message(m: ClientMessageIn):
    """Demo/testing only: make a client say something (e.g. a scam attempt or an injected instruction)."""
    msg = {"message_id": f"msg-{uuid.uuid4().hex[:8]}", **m.model_dump(), "sender": "client",
           "sent_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
    state["messages"].append(msg)
    return msg


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
