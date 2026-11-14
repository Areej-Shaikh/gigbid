"""Memory viewer (Settings screen): see what GigBid has learned, why, and delete any item."""
from fastapi import APIRouter, HTTPException, Request

from agent.config import cfg
from agent.memory.outcomes import sync_outcomes
from agent.memory.store import delete_memory, list_memory
from apps.api.auth.security import User
from apps.api.schemas.models import MemoryItem, MemoryView, SyncResult

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("", response_model=MemoryView)
async def view_memory(request: Request, user: str = User):
    mem = await list_memory(request.app.state.store, user)
    items = {k: [MemoryItem(**{f: v for f, v in i.items() if f in MemoryItem.model_fields}) for i in rows]
             for k, rows in mem.items()}
    m = cfg()["memory"]
    return MemoryView(**items, promotion_rules={"style": m["style"], "outcome": m["outcome"]})


@router.delete("/{kind}/{key}", response_model=MemoryView)
async def forget(kind: str, key: str, request: Request, user: str = User):
    if not await delete_memory(request.app.state.store, user, kind, key):
        raise HTTPException(404, f"nothing called {key!r} in {kind} memory")
    return await view_memory(request, user)


@router.post("/sync-outcomes", response_model=SyncResult)
async def sync(request: Request, user: str = User):
    """Read proposal outcomes from the marketplace and apply the outcome promotion rule."""
    return SyncResult(**await sync_outcomes(request.app.state.toolbox, request.app.state.store, user))
