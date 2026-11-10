"""Bid graph integration tests: real graph + real MCP servers (in-memory) + GigSim (in-process).
LLM_PROFILE=fake, so every node uses its rule-based fallback (no API key needed).

Run: python -m pytest tests/integration -q
"""
import json
from contextlib import AsyncExitStack
from pathlib import Path

import httpx
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from mcp.shared.memory import create_connected_server_and_client_session

import gigsim.app as gigsim
from agent.config import cfg
from agent.graphs.bid_graph import build_bid_graph
from agent.mcp_client import ToolBox
from mcp_servers.marketplace import server as market_server
from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
from mcp_servers.portfolio import server as portfolio_server

pytestmark = pytest.mark.anyio
SEED = json.loads((Path(gigsim.__file__).parent / "seed.json").read_text(encoding="utf-8"))


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROFILE", "fake")
    monkeypatch.setenv("PORTFOLIO_PERSONA", "ai_ml_engineer")
    cfg.cache_clear()
    # small, known data set (independent of your Kaggle build)
    monkeypatch.setattr(gigsim, "JOBS", {j["job_id"]: j for j in SEED["jobs"]})
    monkeypatch.setattr(gigsim, "CLIENTS", {c["client_id"]: c for c in SEED["clients"]})
    monkeypatch.setattr(gigsim, "ERROR_RATE", 0)
    gigsim.state.update(connects=80, proposals={}, idempotency={})
    gigsim.calls.clear()
    monkeypatch.setattr(market_server, "AUDIT_LOG", tmp_path / "audit.jsonl")
    market_server._calls.clear()
    market_server._drafts.clear()
    market_server._draft_keys.clear()
    market_server.set_marketplace(GigSimAdapter(base_url="http://gigsim", transport=httpx.ASGITransport(app=gigsim.app)))
    yield
    cfg.cache_clear()


async def toolbox(stack: AsyncExitStack) -> ToolBox:
    m = await stack.enter_async_context(create_connected_server_and_client_session(market_server.mcp._mcp_server))
    p = await stack.enter_async_context(create_connected_server_and_client_session(portfolio_server.mcp._mcp_server))
    return await ToolBox({"marketplace": m, "portfolio": p}).init()


def run_cfg(tb, thread):
    return {"configurable": {"toolbox": tb, "thread_id": thread}, "recursion_limit": 40}


async def test_scam_job_is_skipped_without_approval():
    async with AsyncExitStack() as stack:
        g = build_bid_graph(InMemorySaver())
        out = await g.ainvoke({"job_id": "job-002"}, run_cfg(await toolbox(stack), "t-scam"))
        assert out["status"] == "skipped"
        assert out["risk"]["level"] == "high" and "unpaid_work" in out["risk"]["flags"]
        assert "__interrupt__" not in out


async def test_good_job_pauses_for_approval_then_submits_once():
    async with AsyncExitStack() as stack:
        tb = await toolbox(stack)
        saver = InMemorySaver()
        g = build_bid_graph(saver)
        out = await g.ainvoke({"job_id": "job-001"}, run_cfg(tb, "t-good"))
        assert "__interrupt__" in out, out.get("decision")
        payload = out["__interrupt__"][0].value
        assert payload["dry_run"]["dry_run"] is True and payload["evidence"]       # preview + evidence shown
        assert gigsim.state["connects"] == 80                                        # nothing spent yet
        # parallel branches all ran before the decision
        nodes = [t["node"] for t in out["trace"]]
        assert {"analyst", "risk", "fit"} <= set(nodes[:5])

        # "crash": build a NEW graph object on the same checkpointer and resume from there
        g2 = build_bid_graph(saver)
        done = await g2.ainvoke(Command(resume={"action": "approve"}), run_cfg(tb, "t-good"))
        assert done["status"] == "submitted"
        spent = 80 - gigsim.state["connects"]
        assert spent == SEED["jobs"][0]["connects_cost"]
        # re-running the submit step (e.g. worker crashed after sending) does not submit twice
        from agent.nodes.approval import submit
        again = await submit(done, run_cfg(tb, "t-good"))
        assert again["submission"]["proposal_id"] == done["submission"]["proposal_id"]
        assert 80 - gigsim.state["connects"] == spent


async def test_every_claim_is_cited_and_verified():
    async with AsyncExitStack() as stack:
        g = build_bid_graph(InMemorySaver())
        out = await g.ainvoke({"job_id": "job-001"}, run_cfg(await toolbox(stack), "t-claims"))
        v = out["verification"]
        assert v["checks"] and all(c["status"] != "unsupported" for c in v["checks"])
        assert out["critique"]["approved"], out["critique"]


async def test_reject_spends_nothing():
    async with AsyncExitStack() as stack:
        tb = await toolbox(stack)
        g = build_bid_graph(InMemorySaver())
        await g.ainvoke({"job_id": "job-001"}, run_cfg(tb, "t-rej"))
        out = await g.ainvoke(Command(resume={"action": "reject", "reason": "too far from my niche"}), run_cfg(tb, "t-rej"))
        assert out["status"] == "rejected" and gigsim.state["connects"] == 80


async def test_edit_is_rechecked_by_compliance_and_saved_for_style_memory():
    async with AsyncExitStack() as stack:
        tb = await toolbox(stack)
        g = build_bid_graph(InMemorySaver())
        first = await g.ainvoke({"job_id": "job-001"}, run_cfg(tb, "t-edit"))
        letter = first["__interrupt__"][0].value["draft"]["cover_letter"]
        edited = letter + " Message me on WhatsApp at +1 555 010 2030."
        out = await g.ainvoke(Command(resume={"action": "edit", "cover_letter": edited}), run_cfg(tb, "t-edit"))
        assert "__interrupt__" in out                                   # back at approval
        assert "WhatsApp" not in out["draft"]["cover_letter"]           # compliance removed it
        assert out["edits"] and out["compliance"]["violations"]


async def test_injected_instruction_is_not_obeyed(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_PERSONA", "fullstack_developer")
    async with AsyncExitStack() as stack:
        g = build_bid_graph(InMemorySaver())
        out = await g.ainvoke({"job_id": "job-004"}, run_cfg(await toolbox(stack), "t-inj"))
        assert "prompt_injection" in out["risk"]["flags"]
        text = (out.get("draft") or {}).get("cover_letter", "")
        assert "10 years" not in text


async def test_marketplace_down_is_reported_not_crashed():
    def refuse(request):
        raise httpx.ConnectError("refused")
    market_server.set_marketplace(GigSimAdapter(base_url="http://gigsim", transport=httpx.MockTransport(refuse), max_retries=0))
    async with AsyncExitStack() as stack:
        g = build_bid_graph(InMemorySaver())
        out = await g.ainvoke({"job_id": "job-001"}, run_cfg(await toolbox(stack), "t-down"))
        assert out["status"] == "marketplace_unavailable"
