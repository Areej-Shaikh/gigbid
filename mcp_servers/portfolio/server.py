"""Portfolio MCP server (Part A1): READ-ONLY access to one freelancer's portfolio evidence.

Good enough to plug into Claude Desktop or Cursor on its own.

Run:  python -m mcp_servers.portfolio.server          (stdio)
Env:  PORTFOLIO_PERSONA = ai_ml_engineer | fullstack_developer | data_analyst
      RAG_VARIANT       = retriever to use (see rag/retriever.py)
"""
# The server is split into core.py (app, index, models), tools.py, resources.py and prompts.py.
from agent.tracing import setup_tracing
from mcp_servers.portfolio import prompts, resources, tools  # noqa: F401  (registers on mcp, in this order)
from mcp_servers.portfolio.core import _cache, mcp, store  # noqa: F401  (re-exported for tests and evals)

if __name__ == "__main__":
    setup_tracing("gigbid-mcp-portfolio")
    mcp.run()
