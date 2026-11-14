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
from agent.tracing import current_trace_id, span, trace_url

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
    """One manager per graph. `key` is the job id (bid graph) or the client id (conversation graph)."""

    def __init__(self, graph, toolbox, index: RunIndex, *, thread_prefix: str = "", input_key: str = "job_id"):
        self.graph, self.toolbox, self.index = graph, toolbox, index
        self.thread_prefix, self.input_key = thread_prefix, input_key
        self.tasks: dict[str, asyncio.Task] = {}
        self.events: dict[str, list[dict]] = {}
        self.listeners: dict[str, list[asyncio.Queue]] = {}
        self.users: dict[str, str] = {}

    def conf(self, job_id: str, user: str | None = None) -> dict:
        user = user or self.users.get(job_id) or "default"
        return {"configurable": {"toolbox": self.toolbox, "thread_id": f"{self.thread_prefix}{job_id}", "user_id": user},
                "recursion_limit": cfg()["budgets"]["max_steps"]}

    def running(self, job_id: str) -> bool:
        t = self.tasks.get(job_id)
        return bool(t and not t.done())

    def _emit(self, job_id: str, event: str, data: Any) -> None:
        e = {"event": event, "data": data}
        self.events.setdefault(job_id, []).append(e)
        for q in self.listeners.get(job_id, []):
            q.put_nowait(e)

    def start(self, job_id: str, resume: dict | None = None, user: str | None = None, restart: bool = False,
              replay_from: str | None = None) -> bool:
        """restart=True starts a NEW pass on a finished thread (conversation graph: the client wrote again).
        replay_from=<checkpoint_id> re-runs the thread from that checkpoint (a fork; history is kept)."""
        if self.running(job_id):
            return False
        if user:
            self.users[job_id] = user          # style / outcome memory is per user
        self.events[job_id] = []
        inp = Command(resume=resume) if resume else (None if replay_from else {self.input_key: job_id})
        task = asyncio.create_task(self._run(job_id, inp, fresh=resume is None and not restart and not replay_from,
                                             checkpoint_id=replay_from))
        task.add_done_callback(lambda t, k=job_id: self._crashed(k, t))
        self.tasks[job_id] = task
        return True

    def _crashed(self, job_id: str, task: asyncio.Task) -> None:
        """A background run must never fail silently: log it and tell the UI (which stops waiting)."""
        if task.cancelled() or task.exception() is None:
            return
        import traceback
        traceback.print_exception(task.exception())
        self._emit(job_id, "error", {"message": f"internal error: {type(task.exception()).__name__}: {task.exception()}"})
        self._emit(job_id, "done", {"status": "error_retry", "next": []})
        for q in self.listeners.get(job_id, []):
            q.put_nowait(None)

    async def _run(self, job_id: str, inp, fresh: bool, checkpoint_id: str | None = None) -> None:
        t0 = time.time()
        existing = await self.graph.aget_state(self.conf(job_id))
        if fresh and existing.values and existing.next:   # paused or crashed mid-run: continue where it stopped
            inp = None
        elif fresh and existing.values and self.input_key == "job_id":
            inp = None                                     # a finished bid analysis is not redone
        run_conf = self.conf(job_id)
        if checkpoint_id:                                  # replay: continue from an earlier checkpoint
            run_conf["configurable"]["checkpoint_id"] = checkpoint_id
        kind = "conversation" if self.input_key == "client_id" else "bid"
        # one span per graph run, child of the API request that started it (same trace id as the UI request)
        with span(f"graph.{kind}", **{"gigbid.thread": run_conf["configurable"]["thread_id"],
                                      "gigbid.user": run_conf["configurable"]["user_id"],
                                      "gigbid.resume": not fresh and checkpoint_id is None, "gigbid.replay_from": checkpoint_id}):
            tid = current_trace_id()
            self.index.update(job_id, trace_id=tid, trace_url=trace_url(tid))
            self._emit(job_id, "start", {"job_id": job_id, "replay_from": checkpoint_id, "trace_id": tid,
                                         "trace_url": trace_url(tid)})
            try:
                async for chunk in self.graph.astream(inp, run_conf, stream_mode="updates"):
                    for node, update in chunk.items():
                        if node == "__interrupt__":
                            self._emit(job_id, "interrupt", {"node": "approval"})
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


class ConversationManager(RunManager):
    """Conversation graph runs: key = client id, thread id = conv-<client_id>."""

    def __init__(self, graph, toolbox, index: RunIndex):
        super().__init__(graph, toolbox, index, thread_prefix="conv-", input_key="client_id")

    def _record(self, client_id: str, v: dict, seconds: float) -> None:
        self.index.update(client_id, status=v.get("status"), intent=(v.get("intent") or {}).get("intent"),
                          job=v.get("job_id"), last_message=(v.get("incoming") or {}).get("message_id"),
                          tokens=v.get("tokens"), duration_s=round(seconds, 2))
