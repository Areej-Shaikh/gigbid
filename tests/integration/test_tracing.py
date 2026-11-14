"""Tracing (E3) + PII masking in traces (E4): one trace id from the request through the graph and every MCP
server into the audit log; exported spans never contain emails or phone numbers."""
import json
from contextlib import AsyncExitStack
from pathlib import Path

import httpx
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from mcp.shared.memory import create_connected_server_and_client_session
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import gigsim.app as gigsim
from agent.config import cfg
from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from agent.mcp_client import ToolBox
from agent.tracing import MaskingExporter, current_trace_id, span
from mcp_servers.marketplace import server as market_server
from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
from mcp_servers.portfolio import server as portfolio_server
from mcp_servers.workspace import server as workspace_server

pytestmark = pytest.mark.anyio
SEED = json.loads((Path(gigsim.__file__).parent / "seed.json").read_text(encoding="utf-8"))
EXPORTED = InMemorySpanExporter()


@pytest.fixture(scope="module", autouse=True)
def provider():
    p = TracerProvider()
    p.add_span_processor(SimpleSpanProcessor(MaskingExporter(EXPORTED)))   # same masking as production
    trace.set_tracer_provider(p)
    yield p


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROFILE", "fake")
    monkeypatch.setenv("PORTFOLIO_PERSONA", "ai_ml_engineer")
    cfg.cache_clear()
    monkeypatch.setattr(gigsim, "JOBS", {j["job_id"]: j for j in SEED["jobs"]})
    monkeypatch.setattr(gigsim, "CLIENTS", {c["client_id"]: c for c in SEED["clients"]})
    monkeypatch.setattr(gigsim, "ERROR_RATE", 0)
    gigsim.state.update(connects=80, proposals={}, idempotency={}, messages=[])
    gigsim.calls.clear()
    market_server._calls.clear()
    monkeypatch.setattr(market_server, "AUDIT_LOG", tmp_path / "audit.jsonl")
    market_server.set_marketplace(GigSimAdapter(base_url="http://gigsim", transport=httpx.ASGITransport(app=gigsim.app)))
    monkeypatch.setattr(workspace_server, "DATA", tmp_path / "workspace.json")
    EXPORTED.clear()
    yield
    cfg.cache_clear()


async def toolbox(stack):
    sessions = {}
    for name, srv in (("marketplace", market_server), ("portfolio", portfolio_server), ("workspace", workspace_server)):
        sessions[name] = await stack.enter_async_context(create_connected_server_and_client_session(srv.mcp._mcp_server))
    return await ToolBox(sessions).init()


async def test_one_trace_id_from_request_through_graph_mcp_servers_and_audit_log():
    async with AsyncExitStack() as stack:
        tb = await toolbox(stack)
        with span("http.request POST /api/runs/job-001"):              # stands in for the API request span
            tid = current_trace_id()
            await build_bid_graph(InMemorySaver()).ainvoke(
                {"job_id": "job-001"}, {"configurable": {"toolbox": tb, "thread_id": "t-trace"}, "recursion_limit": 40})
    # GigBid's own spans (tracer "gigbid"); GigSim, the simulated marketplace, is not part of GigBid
    spans = [s for s in EXPORTED.get_finished_spans() if s.instrumentation_scope.name == "gigbid"]
    names = {s.name for s in spans}
    assert {"mcp.call.get_job", "mcp.marketplace.get_job", "mcp.portfolio.search_evidence", "llm.writer"} <= names
    assert {format(s.context.trace_id, "032x") for s in spans} == {tid}      # ONE trace id everywhere
    server_span = next(s for s in spans if s.name == "mcp.marketplace.get_job")
    client_span = next(s for s in spans if s.name == "mcp.call.get_job")
    assert server_span.parent.span_id == client_span.context.span_id        # MCP server span is a child of the call
    audit = [json.loads(x) for x in market_server.AUDIT_LOG.read_text(encoding="utf-8").splitlines()]
    assert audit and {a["trace_id"] for a in audit} == {tid}                  # audit log carries the same id
    writer = next(s for s in spans if s.name == "llm.writer")
    assert {"gigbid.model", "gigbid.tokens.input", "gigbid.cost_usd"} <= set(writer.attributes)


async def test_emails_and_phones_never_reach_exported_spans():
    async with AsyncExitStack() as stack:
        tb = await toolbox(stack)
        gigsim.dev_client_message(gigsim.ClientMessageIn(
            client_id="cl-001", job_id="job-001",
            text="Email me at jane.doe@example.com or call +1 555 010 2030, card 4111 1111 1111 1111"))
        with span("http.request POST /api/conversations/cl-001/run", **{"client.note": "reach me at bob@example.org"}):
            await build_conversation_graph(InMemorySaver()).ainvoke(
                {"client_id": "cl-001"}, {"configurable": {"toolbox": tb, "thread_id": "conv-cl-001"}, "recursion_limit": 30})
    dump = json.dumps([{"a": dict(s.attributes or {}), "e": [dict(e.attributes or {}) for e in s.events]}
                       for s in EXPORTED.get_finished_spans()], default=str)
    assert "[email]" in dump                                                 # masking ran
    for secret in ("jane.doe@example.com", "bob@example.org", "555 010 2030", "4111 1111 1111 1111"):
        assert secret not in dump
