"""Unit tests for the Marketplace MCP server, using an in-memory MCP client + in-process GigSim.

Run from the project root:  python -m pytest mcp_servers/marketplace/tests -q
"""
import json

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

import gigsim.app as gigsim
from mcp_servers.marketplace import server
from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def setup(tmp_path, monkeypatch):
    gigsim.ERROR_RATE = 0                      # no random failures in unit tests
    gigsim.calls.clear()
    monkeypatch.setattr(server, "AUDIT_LOG", tmp_path / "audit.jsonl")
    server._calls.clear()
    server.set_marketplace(GigSimAdapter(base_url="http://gigsim",
                                         transport=httpx.ASGITransport(app=gigsim.app)))
    yield


async def call(session, tool, **args):
    res = await session.call_tool(tool, args)
    return res


async def test_tools_have_schemas_and_annotations():
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        assert set(tools) == {"search_jobs", "get_job", "get_client_history", "get_connects_balance",
                              "get_price_stats", "list_messages", "list_proposals", "create_proposal_draft",
                              "submit_proposal", "send_message"}
        assert tools["search_jobs"].annotations.readOnlyHint is True
        assert tools["submit_proposal"].annotations.destructiveHint is True
        assert all(t.outputSchema for t in tools.values())


async def test_search_hides_answer_labels():
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as s:
        res = await call(s, "search_jobs", query="", limit=50)
        jobs = res.structuredContent["jobs"]
        assert jobs and all("labels" not in j and "source" not in j for j in jobs)


async def test_draft_dry_run_then_submit_exactly_once():
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as s:
        job = (await call(s, "search_jobs", limit=1)).structuredContent["jobs"][0]
        start = (await call(s, "get_connects_balance")).structuredContent["balance"]
        draft = (await call(s, "create_proposal_draft", job_id=job["job_id"], bid_amount=300,
                            idempotency_key="draft-key-1",
                            cover_letter="Hello, I have built similar systems before. " * 3)).structuredContent

        preview = (await call(s, "submit_proposal", draft_id=draft["draft_id"],
                              idempotency_key="submit-key-1")).structuredContent   # dry_run default
        assert preview["dry_run"] and preview["would_send"]["job_id"] == job["job_id"]
        assert (await call(s, "get_connects_balance")).structuredContent["balance"] == start  # nothing spent

        r1 = (await call(s, "submit_proposal", draft_id=draft["draft_id"], idempotency_key="submit-key-1",
                         dry_run=False)).structuredContent
        r2 = (await call(s, "submit_proposal", draft_id=draft["draft_id"], idempotency_key="submit-key-1",
                         dry_run=False)).structuredContent   # retry
        assert r1["proposal_id"] == r2["proposal_id"]
        end = (await call(s, "get_connects_balance")).structuredContent["balance"]
        assert end == start - job["connects_cost"]            # charged once


async def test_invalid_input_rejected():
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as s:
        res = await call(s, "create_proposal_draft", job_id="job-001", bid_amount=-5,
                         idempotency_key="bad-key-1", cover_letter="too short")
        assert res.isError


async def test_marketplace_down_gives_clear_error():
    def refuse(request):
        raise httpx.ConnectError("connection refused")
    server.set_marketplace(GigSimAdapter(base_url="http://gigsim", transport=httpx.MockTransport(refuse),
                                         max_retries=1))
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as s:
        res = await call(s, "search_jobs", query="python")
        assert res.isError and "marketplace_unavailable" in res.content[0].text


async def test_audit_log_written_and_masked():
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as s:
        await call(s, "send_message", client_id="cl-001", text="Mail me at test@example.com",
                   idempotency_key="msg-key-1", dry_run=False)
    lines = server.AUDIT_LOG.read_text().splitlines()
    entry = json.loads(lines[-1])
    assert entry["tool"] == "send_message" and "test@example.com" not in lines[-1]
