# ADR 0002: All external access through MCP servers with per-agent allowlists

**Status:** accepted

## Context
Agents read untrusted text (job posts, client messages). If a model is manipulated, the damage it can do
is limited by the tools it can reach.

## Decision
Marketplace, portfolio and workspace are separate MCP servers. The agent side calls them only through
`ToolBox.call(agent, tool)`, which checks `config.yaml → tool_allowlist`. Read-only agents get no tools;
write tools are reachable only from nodes after the approval interrupt; previews force `dry_run=True`.
The marketplace sits behind one port with swappable adapters (GigSim now, a live API later).

## Consequences
+ Least privilege is enforced in one place and visible in config; the audit log records every call with its trace id.
+ The same servers work over stdio (local) and Streamable HTTP with bearer tokens.
− One more process per server and slightly more latency than in-process function calls.
