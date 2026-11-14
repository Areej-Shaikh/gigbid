"""MCP contract tests (A7): every tool's name, input schema, output schema and annotations are snapshotted.
CI fails when a tool signature changes unintentionally.

Changed a tool ON PURPOSE? Regenerate the snapshots and commit them with the change:
    UPDATE_SNAPSHOTS=1 python -m pytest tests/contract -q
"""
import json
import os
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.marketplace import server as marketplace
from mcp_servers.portfolio import server as portfolio
from mcp_servers.workspace import server as workspace

pytestmark = pytest.mark.anyio
SNAPSHOTS = Path(__file__).parent / "snapshots"
SERVERS = {"marketplace": marketplace, "portfolio": portfolio, "workspace": workspace}


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def surface(srv) -> dict:
    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as s:
        tools = {t.name: {"description": (t.description or "").strip(), "input": t.inputSchema,
                          "output": t.outputSchema,
                          "annotations": t.annotations.model_dump(exclude_none=True) if t.annotations else {}}
                 for t in (await s.list_tools()).tools}
        templates = sorted(t.uriTemplate for t in (await s.list_resource_templates()).resourceTemplates)
        prompts = sorted(p.name for p in (await s.list_prompts()).prompts)
    return {"tools": dict(sorted(tools.items())), "resource_templates": templates, "prompts": prompts}


@pytest.mark.parametrize("name", sorted(SERVERS))
async def test_tool_surface_matches_snapshot(name):
    current = await surface(SERVERS[name])
    path = SNAPSHOTS / f"{name}.json"
    if os.getenv("UPDATE_SNAPSHOTS") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    assert path.exists(), f"no snapshot for {name}: run UPDATE_SNAPSHOTS=1 python -m pytest tests/contract"
    saved = json.loads(path.read_text(encoding="utf-8"))
    changed = sorted(t for t in set(saved["tools"]) | set(current["tools"])
                     if saved["tools"].get(t) != current["tools"].get(t))
    assert not changed, (f"{name}: tool signature changed for {changed}. If intended, regenerate the snapshot "
                         "(UPDATE_SNAPSHOTS=1) and commit it with the change.")
    assert saved["resource_templates"] == current["resource_templates"]
    assert saved["prompts"] == current["prompts"]


async def test_write_tools_are_never_marked_read_only():
    for name, srv in SERVERS.items():
        for tool, spec in (await surface(srv))["tools"].items():
            writes = tool.startswith(("create_", "submit_", "send_"))
            assert spec["annotations"].get("readOnlyHint") is (not writes), f"{name}.{tool} has a wrong readOnlyHint"
