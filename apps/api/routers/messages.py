"""Client messages from the marketplace (read-only; replies are drafted and approved in routers/conversations.py)."""
from fastapi import APIRouter, Request

from apps.api.auth.security import User
from apps.api.schemas.models import Message, MessageList

router = APIRouter(tags=["messages"])


@router.get("/messages", response_model=MessageList)
async def messages(request: Request, user: str = User):
    res = await request.app.state.toolbox.call("api", "list_messages")
    return MessageList(messages=[Message(**m) for m in res["messages"]])
