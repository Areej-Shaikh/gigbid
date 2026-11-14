"""Durability (C6): a paused approval survives a crash, and the proposal is submitted exactly once.

`test_backend_is_chosen_by_config` always runs. The Postgres tests run when TEST_DATABASE_URL points at a
Postgres database and the OS is not Windows (psycopg async needs a Linux event loop), e.g. in CI:
    TEST_DATABASE_URL=postgresql://gigbid:gigbid@localhost:5432/gigbid python -m pytest tests/integration -q
"""
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

import httpx
import pytest
from langgraph.types import Command
from mcp.shared.memory import create_connected_server_and_client_session

import gigsim.app as gigsim
from agent import persistence
from agent.config import cfg
from agent.graphs.bid_graph import build_bid_graph
from agent.mcp_client import ToolBox
from mcp_servers.marketplace import server as market_server
from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
from mcp_servers.portfolio import server as portfolio_server

pytestmark = pytest.mark.anyio
SEED = json.loads((Path(gigsim.__file__).parent / "seed.json").read_text(encoding="utf-8"))
PG = os.getenv("TEST_DATABASE_URL", "")
needs_pg = pytest.mark.skipif(not PG or sys.platform == "win32", reason="set TEST_DATABASE_URL (Linux) to run")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_backend_is_chosen_by_config(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert persistence.backend() == "sqlite"
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@db:5432/x")     # Render-style scheme is accepted
    assert persistence.backend() == "postgres" and persistence._pg_url().startswith("postgresql://")


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROFILE", "fake")
    monkeypatch.setenv("PORTFOLIO_PERSONA", "ai_ml_engineer")
    monkeypatch.setenv("DATABASE_URL", PG)
    cfg.cache_clear()
    monkeypatch.setattr(gigsim, "JOBS", {j["job_id"]: j for j in SEED["jobs"]})
    monkeypatch.setattr(gigsim, "CLIENTS", {c["client_id"]: c for c in SEED["clients"]})
    monkeypatch.setattr(gigsim, "ERROR_RATE", 0)
    gigsim.state.update(connects=80, proposals={}, idempotency={}, messages=[])
    monkeypatch.setattr(market_server, "AUDIT_LOG", tmp_path / "audit.jsonl")
    market_server.set_marketplace(GigSimAdapter(base_url="http://gigsim", transport=httpx.ASGITransport(app=gigsim.app)))
    yield
    cfg.cache_clear()


async def toolbox(stack):
    m = await stack.enter_async_context(create_connected_server_and_client_session(market_server.mcp._mcp_server))
    p = await stack.enter_async_context(create_connected_server_and_client_session(portfolio_server.mcp._mcp_server))
    return await ToolBox({"marketplace": m, "portfolio": p}).init()


@needs_pg
async def test_crash_while_waiting_then_approve_submits_exactly_once(env):
    thread = f"t-durable-{os.getpid()}"
    async with AsyncExitStack() as stack:                       # "process 1": runs until the approval pause
        tb = await toolbox(stack)
        saver, store = await stack.enter_async_context(persistence.open_persistence())
        conf = {"configurable": {"toolbox": tb, "thread_id": thread}, "recursion_limit": 40}
        out = await build_bid_graph(saver, store).ainvoke({"job_id": "job-001"}, conf)
        assert "__interrupt__" in out
    # process 1 is gone (connections closed, nothing in memory). "Process 2" reopens Postgres and approves.
    async with AsyncExitStack() as stack:
        tb = await toolbox(stack)
        saver, store = await stack.enter_async_context(persistence.open_persistence())
        g = build_bid_graph(saver, store)
        conf = {"configurable": {"toolbox": tb, "thread_id": thread}, "recursion_limit": 40}
        assert (await g.aget_state(conf)).next == ("human_approval",)
        out = await g.ainvoke(Command(resume={"action": "approve"}), conf)
        assert out["status"] == "submitted"
        assert len(gigsim.state["proposals"]) == 1 and gigsim.state["connects"] == 80 - SEED["jobs"][0]["connects_cost"]
