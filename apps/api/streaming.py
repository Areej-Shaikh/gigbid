"""Runs the bid graph in BACKGROUND tasks and streams node-by-node progress over SSE.

- A run keeps going even if the browser tab closes (the task is not tied to the request).
- Late subscribers get the events so far replayed, then live events.
- Everything is checkpointed, so a refresh (or API restart) never loses a pending approval.
"""
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from langgraph.types import Command

from agent.config import cfg

INDEX = Path("data/processed/runs.json")


class RunIndex:
    """Small JSON index of runs (for the inbox, pipeline and analytics screens)."""

    def __init__(self, path: Path = INDEX):
        self.path = path
        self.data: dict[str, dict] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def update(self, job_id: str, **fields) -> None:
        row = self.data.setdefault(job_id, {"job_id": job_id})
        row.update({k: v for k, v in fields.items() if v is not None})
        row["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1), encoding="utf-8")


class RunManager:
    def __init__(self, graph, toolbox, index: RunIndex):
        self.graph, self.toolbox, self.index = graph, toolbox, index
        self.tasks: dict[str, asyncio.Task] = {}
        self.events: dict[str, list[dict]] = {}
        self.listeners: dict[str, list[asyncio.Queue]] = {}

    def conf(self, job_id: str) -> dict:
        return {"configurable": {"toolbox": self.toolbox, "thread_id": job_id},
                "recursion_limit": cfg()["budgets"]["max_steps"]}

    def running(self, job_id: str) -> bool:
        t = self.tasks.get(job_id)
        return bool(t and not t.done())

    def _emit(self, job_id: str, event: str, data: Any) -> None:
        e = {"event": event, "data": data}
        self.events.setdefault(job_id, []).append(e)
        for q in self.listeners.get(job_id, []):
            q.put_nowait(e)

    def start(self, job_id: str, resume: dict | None = None) -> bool:
        if self.running(job_id):
            return False
        self.events[job_id] = []
        inp = Command(resume=resume) if resume else {"job_id": job_id}
        self.tasks[job_id] = asyncio.create_task(self._run(job_id, inp, fresh=resume is None))
        return True

    async def _run(self, job_id: str, inp, fresh: bool) -> None:
        t0 = time.time()
        existing = await self.graph.aget_state(self.conf(job_id))
        if fresh and existing.values:      # already analysed earlier: just continue where it stopped
            inp = None
        self._emit(job_id, "start", {"job_id": job_id})
        try:
            async for chunk in self.graph.astream(inp, self.conf(job_id), stream_mode="updates"):
                for node, update in chunk.items():
                    if node == "__interrupt__":
                        self._emit(job_id, "interrupt", {"node": "human_approval"})
                        continue
                    update = update or {}
                    self._emit(job_id, "node", {"node": node, "status": update.get("status"),
                                                "trace": update.get("trace", [])})
        except Exception as e:  # noqa: BLE001 - shown in the UI, thread stays resumable
            self._emit(job_id, "error", {"message": f"{type(e).__name__}: {e}"})
            self.index.update(job_id, status="error_retry")
        state = await self.graph.aget_state(self.conf(job_id))
        self._record(job_id, state.values, time.time() - t0)
        self._emit(job_id, "done", {"status": state.values.get("status"), "next": list(state.next)})
        for q in self.listeners.get(job_id, []):
            q.put_nowait(None)

    def _record(self, job_id: str, v: dict, seconds: float) -> None:
        row = self.index.data.get(job_id, {})
        self.index.update(
            job_id, title=(v.get("job") or {}).get("title"), status=v.get("status"),
            action=(v.get("decision") or {}).get("action"), fit=(v.get("fit") or {}).get("fit_score"),
            risk=(v.get("risk") or {}).get("level"), risk_flags=(v.get("risk") or {}).get("flags"),
            price=(v.get("price") or {}).get("amount"), tokens=v.get("tokens"),
            connects_spent=(v.get("submission") or {}).get("connects_cost"),
            reject_reason=(v.get("approval") or {}).get("reason"),
            skip_reasons=(v.get("decision") or {}).get("reasons"),
            duration_s=round(row.get("duration_s", 0) + seconds, 2))

    async def subscribe(self, job_id: str):
        q: asyncio.Queue = asyncio.Queue()
        for e in self.events.get(job_id, []):
            q.put_nowait(e)
        if not self.running(job_id):
            q.put_nowait(None)
        self.listeners.setdefault(job_id, []).append(q)
        try:
            while True:
                e = await q.get()
                if e is None:
                    break
                yield {"event": e["event"], "data": json.dumps(e["data"], default=str)}
        finally:
            self.listeners[job_id].remove(q)
