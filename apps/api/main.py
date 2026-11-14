"""GigBid API (FastAPI).

Run (from the project root, GigSim must be running on :8001):
    python -m apps.api.main
Do NOT use `uvicorn --reload` on Windows: reload mode uses an event loop that cannot start
the MCP server subprocesses.
"""
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # noqa: E402

from agent.config import cfg  # noqa: E402
from agent.graphs.bid_graph import build_bid_graph  # noqa: E402
from agent.graphs.conversation_graph import build_conversation_graph  # noqa: E402
from agent.mcp_client import open_toolbox  # noqa: E402
from agent.memory.store import open_store  # noqa: E402
from apps.api.routers import analytics, auth, conversations, jobs, memory, runs  # noqa: E402
from apps.api.schemas.models import Health  # noqa: E402
from apps.api.streaming import ConversationManager, RunIndex, RunManager  # noqa: E402

DB = Path("data/processed/checkpoints.sqlite")
MEMORY_DB = Path("data/processed/memory.sqlite")          # long-term memory (style + outcome), kept apart
WEB_DIST = Path("apps/web/dist")


@asynccontextmanager
async def lifespan(app: FastAPI):
    DB.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(DB)) as saver, open_store(MEMORY_DB) as store, \
            open_toolbox() as tb:
        app.state.toolbox, app.state.store = tb, store
        app.state.runs = RunManager(build_bid_graph(saver, store), tb, RunIndex())
        app.state.convs = ConversationManager(build_conversation_graph(saver, store), tb,
                                              RunIndex(Path("data/processed/conversations.json")))
        yield


app = FastAPI(title="GigBid API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
for r in (auth.router, jobs.router, runs.router, analytics.router, conversations.router, memory.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health", response_model=Health, tags=["health"])
async def health(request: Request):
    try:
        res = await request.app.state.toolbox.sessions["marketplace"].call_tool("get_connects_balance", {})
        text = res.content[0].text if res.isError and res.content else ""
        market = "down" if res.isError and "rate_limited" not in text else "ok"   # busy is not down
    except Exception:  # noqa: BLE001
        market = "down"
    return Health(api="ok", marketplace=market, llm_profile=cfg()["profile"])


# production: serve the built React app from the same server (one URL to deploy)
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        return FileResponse(WEB_DIST / "index.html")


if __name__ == "__main__":
    import uvicorn
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))   # hosts set PORT
