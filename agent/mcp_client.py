"""MCP client side (A6): every agent gets only the tools in its allowlist, with a timeout.

Production: open_toolbox() starts the MCP servers from config (stdio or HTTP) and keeps
one session per server open. Tests: build ToolBox directly from in-memory sessions.
"""
import asyncio
import os
import sys
from contextlib import AsyncExitStack, asynccontextmanager

from mcp import ClientSession

from agent.config import cfg
from agent.tracing import inject_meta, span


class ToolCallError(Exception):
    pass


class ToolBox:
    def __init__(self, sessions: dict[str, ClientSession], timeout_s: float = 30):
        self.sessions = sessions
        self.timeout_s = timeout_s
        self.server_of: dict[str, str] = {}

    async def init(self) -> "ToolBox":
        for server, s in self.sessions.items():
            for t in (await s.list_tools()).tools:
                self.server_of[t.name] = server
        return self

    async def call(self, agent: str, tool: str, **args) -> dict:
        allowed = cfg()["tool_allowlist"].get(agent, [])
        if tool not in allowed:
            raise PermissionError(f"agent '{agent}' may not call '{tool}' (allowed: {allowed})")
        if tool not in self.server_of:
            raise ToolCallError(f"tool '{tool}' not available (is its MCP server running?)")
        server = self.server_of[tool]
        with span(f"mcp.call.{tool}", **{"mcp.server": server, "mcp.tool": tool, "gigbid.agent": agent}) as sp:
            for attempt in range(4):
                try:          # the trace context travels to the MCP server in the request _meta (E3)
                    res = await asyncio.wait_for(self.sessions[server].call_tool(tool, args, meta=inject_meta() or None),
                                                 self.timeout_s)
                except asyncio.TimeoutError:
                    sp.set_attribute("gigbid.error", "timeout")
                    raise ToolCallError(f"marketplace_unavailable: {tool} timed out after {self.timeout_s}s")
                if not res.isError:
                    return res.structuredContent or {}
                text = res.content[0].text if res.content else f"{tool} failed"
                if "rate_limited" not in text or attempt == 3:
                    sp.set_attribute("gigbid.error", text[:200])
                    raise ToolCallError(text)
                sp.add_event("rate_limited_retry", {"attempt": attempt + 1})
                await asyncio.sleep(3 * 2 ** attempt)   # polite: back off and retry when rate-limited
            raise ToolCallError(f"{tool} failed")


@asynccontextmanager
async def open_toolbox():
    from langchain_mcp_adapters.client import MultiServerMCPClient
    conns = {}
    for name, c in cfg()["mcp_servers"].items():
        c = dict(c)
        if c["transport"] == "stdio":
            c["env"] = {**os.environ, **c.get("env", {})}
            if c.get("command") == "python":  # same interpreter as GigBid, not whatever is first on PATH
                c["command"] = sys.executable
        conns[name] = c
    client = MultiServerMCPClient(conns)
    async with AsyncExitStack() as stack:
        sessions = {n: await stack.enter_async_context(client.session(n)) for n in conns}
        yield await ToolBox(sessions).init()
