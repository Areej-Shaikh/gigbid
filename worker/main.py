"""Background worker (E1): scheduled scouting of saved searches, with de-duplication, on Arq + Redis.

  arq worker.main.WorkerSettings          (docker compose runs this as the `worker` service)

Each round (every scout.interval_hours, and once at start-up):
  1. run every saved search in config.yaml -> scout.saved_searches through the API (same MCP tools, same auth),
  2. drop jobs already seen (Redis set per user) or already analysed (the API reports a status),
  3. enqueue `analyse` for at most scout.max_new_jobs_per_round new jobs. Arq job ids are
     "analyse:<user>:<job_id>", so the same job is never queued twice, even across worker restarts.
`analyse` asks the API to start the bid graph for that user; the run continues in the API's background runner up to
the approval interrupt and is checkpointed in Postgres, so the user finds it waiting in the inbox. Nothing is ever
submitted by the worker: submission only happens after approval, with an idempotency key.
"""
import os
from dataclasses import dataclass

import httpx
from arq import cron
from arq.connections import RedisSettings

from agent.config import cfg
from apps.api.auth.security import make_token

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")


@dataclass
class Found:
    user: str
    job_id: str


def plan_new_jobs(user: str, jobs: list[dict], seen: set[str], limit: int) -> list[Found]:
    """Pure de-duplication rule (unit-tested): skip seen or already-analysed jobs, keep order, cap the round."""
    out, picked = [], set()
    for j in jobs:
        jid = j["job_id"]
        if jid in seen or jid in picked or j.get("status") or j.get("action"):
            continue
        picked.add(jid)
        out.append(Found(user, jid))
        if len(out) >= limit:
            break
    return out


def _client(user: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=API_URL, timeout=60, headers={"Authorization": f"Bearer {make_token(user)}"})


async def scout(ctx) -> dict:
    s = cfg()["scout"]
    redis = ctx["redis"]
    queued: list[str] = []
    budget = int(s.get("max_new_jobs_per_round", 10))
    for search in s.get("saved_searches", []):
        user = search["user"]
        try:
            async with _client(user) as api:
                r = await api.get("/api/jobs", params={"q": search["query"], "limit": search.get("limit", 20)})
        except httpx.HTTPError as e:        # API not up yet / restarting: skip this round, try again next round
            print(f"scout: API unreachable ({type(e).__name__}); retrying next round", flush=True)
            return {"queued": queued, "skipped": "api_unreachable"}
        if r.status_code != 200:            # marketplace down: try again next round (degraded, not an error storm)
            continue
        seen = {m.decode() if isinstance(m, bytes) else m for m in await redis.smembers(f"gigbid:seen:{user}")}
        for f in plan_new_jobs(user, r.json()["jobs"], seen, budget - len(queued)):
            await redis.sadd(f"gigbid:seen:{user}", f.job_id)
            if await redis.enqueue_job("analyse", f.user, f.job_id, _job_id=f"analyse:{f.user}:{f.job_id}"):
                queued.append(f"{f.user}:{f.job_id}")
        if len(queued) >= budget:
            break
    print(f"scout round: queued {len(queued)} new jobs {queued}", flush=True)
    return {"queued": queued}


async def analyse(ctx, user: str, job_id: str) -> dict:
    async with _client(user) as api:
        r = await api.post(f"/api/runs/{job_id}")
    r.raise_for_status()                    # Arq retries the job with backoff (max_tries)
    return r.json()


def _hours() -> set[int]:
    every = max(1, int(cfg()["scout"].get("interval_hours", 2)))
    return set(range(0, 24, every))


class WorkerSettings:
    functions = [analyse]
    cron_jobs = [cron(scout, hour=_hours(), minute=0, run_at_startup=True, unique=True)]
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379"))
    max_tries = 3
    job_timeout = 600
