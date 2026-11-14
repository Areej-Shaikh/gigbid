"""Workspace MCP server (A3), tested through an in-memory MCP client (A7)."""
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.workspace import server

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def tmp_data(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "DATA", tmp_path / "workspace.json")


async def call(s, tool, **args):
    res = await s.call_tool(tool, args)
    return res.structuredContent, res.isError


async def test_tools_and_annotations():
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        assert set(tools) == {"free_slots", "create_hold", "list_holds", "create_email_draft"}
        assert tools["free_slots"].annotations.readOnlyHint is True
        assert tools["create_hold"].annotations.readOnlyHint is False
        assert tools["create_hold"].annotations.idempotentHint is True


async def test_slots_skip_holds_and_holds_are_idempotent():
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as s:
        slots, _ = await call(s, "free_slots", days_ahead=5, duration_min=30, limit=3)
        assert len(slots["slots"]) == 3
        first = slots["slots"][0]["start"]
        h1, _ = await call(s, "create_hold", start=first, title="Interview: test", idempotency_key="conv-x-msg-1-hold")
        h2, _ = await call(s, "create_hold", start=first, title="Interview: test", idempotency_key="conv-x-msg-1-hold")
        assert h1["hold_id"] == h2["hold_id"]                       # retried call -> same hold, not two
        assert len((await call(s, "list_holds"))[0]["holds"]) == 1
        again, _ = await call(s, "free_slots", days_ahead=5, duration_min=30, limit=3)
        assert first not in [x["start"] for x in again["slots"]]     # booked slot is no longer offered


async def test_bad_input_is_rejected():
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as s:
        _, err = await call(s, "create_hold", start="2020-01-01T10:00", title="Old", idempotency_key="key-12345678")
        assert err                                                   # past time
        _, err = await call(s, "free_slots", days_ahead=99)
        assert err                                                   # schema limit (1..14)
        d, err = await call(s, "create_email_draft", to="client@example.com", subject="Hi", body="Draft only",
                            idempotency_key="mail-12345678")
        assert not err and d["status"] == "draft"                    # drafts are never sent
