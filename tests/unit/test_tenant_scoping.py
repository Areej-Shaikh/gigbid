"""Tenant scoping (E4): runs, threads, events and index rows belong to the user who started them."""
import asyncio
from typing import TypedDict

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from apps.api.streaming import RunIndex, RunManager, scoped


class S(TypedDict, total=False):
    job_id: str
    status: str


def tiny_graph():
    g = StateGraph(S)
    g.add_node("work", lambda s, config: {"status": f"done for {config['configurable']['user_id']}"})
    g.add_edge(START, "work")
    g.add_edge("work", END)
    return g.compile(checkpointer=InMemorySaver())


def test_same_job_two_users_two_isolated_runs(tmp_path):
    async def go():
        m = RunManager(tiny_graph(), toolbox=None, index=RunIndex(tmp_path / "runs.json"))
        assert m.start("job-1", user="alice") and m.start("job-1", user="bob")   # not "already running"
        await asyncio.gather(*m.tasks.values())
        a = await m.graph.aget_state(m.conf("job-1", "alice"))
        b = await m.graph.aget_state(m.conf("job-1", "bob"))
        assert a.values["status"] == "done for alice" and b.values["status"] == "done for bob"
        assert m.conf("job-1", "alice")["configurable"]["thread_id"] != m.conf("job-1", "bob")["configurable"]["thread_id"]
        # a user who never ran the job sees nothing
        assert not (await m.graph.aget_state(m.conf("job-1", "mallory"))).values
        assert [r["job_id"] for r in m.index.rows("alice")] == ["job-1"]
        assert m.index.rows("mallory") == [] and m.index.row("job-1", "mallory") == {}
        events = [e async for e in m.subscribe("job-1", "mallory")]
        assert events == []
        assert any(e["event"] == "done" for e in [x async for x in m.subscribe("job-1", "alice")])
    asyncio.run(go())


def test_a_run_always_needs_a_user():
    with pytest.raises(ValueError):
        scoped("job-1", "")
