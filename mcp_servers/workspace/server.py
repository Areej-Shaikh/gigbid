"""Workspace MCP server (Part A3): calendar slots, tentative interview holds and email drafts.

Backed by a LOCAL MOCK (a JSON file), not Google Calendar / Gmail: nothing ever leaves the machine.
The agent only sees MCP tools, so swapping in the official Google APIs later changes this file only.

Run:  python -m mcp_servers.workspace.server          (stdio)
Env:  WORKSPACE_DATA   = path of the JSON file (default data/processed/workspace.json)
      WORKSPACE_HOURS  = working hours, e.g. "9-17" (default)
"""
import json
import os
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from agent.tracing import setup_tracing, traced_tool

mcp = FastMCP("gigbid-workspace")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
DATA = Path(os.getenv("WORKSPACE_DATA", "data/processed/workspace.json"))


def _load() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {"holds": {}, "drafts": {}}


def _save(d: dict) -> None:
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(d, indent=1), encoding="utf-8")


def _hours() -> tuple[int, int]:
    a, b = os.getenv("WORKSPACE_HOURS", "9-17").split("-")
    return int(a), int(b)


# ---------------------------------------------------------------- models
class Slot(BaseModel):
    start: str = Field(description="ISO 8601 local time, e.g. 2026-11-17T10:00")
    end: str


class SlotList(BaseModel):
    slots: list[Slot]


class Hold(BaseModel):
    hold_id: str
    start: str
    end: str
    title: str
    status: str = "tentative"


class HoldList(BaseModel):
    holds: list[Hold]


class EmailDraft(BaseModel):
    draft_id: str
    to: str
    subject: str
    body: str
    status: str = "draft"     # never sent by this server


# ---------------------------------------------------------------- tools
@mcp.tool(annotations=READ)
@traced_tool("workspace")
def free_slots(
    days_ahead: Annotated[int, Field(ge=1, le=14, description="How many days to look ahead, starting tomorrow")] = 5,
    duration_min: Annotated[int, Field(ge=15, le=120)] = 30,
    limit: Annotated[int, Field(ge=1, le=10)] = 3,
) -> SlotList:
    """Free calendar slots on weekdays within working hours, skipping existing holds."""
    h0, h1 = _hours()
    busy = [(datetime.fromisoformat(h["start"]), datetime.fromisoformat(h["end"])) for h in _load()["holds"].values()]
    out, day = [], date.today()
    for _ in range(days_ahead):
        day += timedelta(days=1)
        if day.weekday() >= 5:
            continue
        t = datetime.combine(day, datetime.min.time()).replace(hour=h0)
        while t + timedelta(minutes=duration_min) <= t.replace(hour=h1, minute=0):
            end = t + timedelta(minutes=duration_min)
            if not any(t < b1 and end > b0 for b0, b1 in busy):
                out.append(Slot(start=t.isoformat(timespec="minutes"), end=end.isoformat(timespec="minutes")))
                break                            # one offer per day: the client gets a choice of days
            t += timedelta(minutes=30)
        if len(out) >= limit:
            break
    return SlotList(slots=out)


@mcp.tool(annotations=WRITE)
@traced_tool("workspace")
def create_hold(
    start: Annotated[str, Field(description="ISO start time from free_slots")],
    title: Annotated[str, Field(min_length=3, max_length=200)],
    idempotency_key: Annotated[str, Field(min_length=8, max_length=100)],
    duration_min: Annotated[int, Field(ge=15, le=120)] = 30,
) -> Hold:
    """Put a TENTATIVE interview hold on the calendar. Same idempotency_key returns the same hold."""
    d = _load()
    if idempotency_key in d["holds"]:
        return Hold(**d["holds"][idempotency_key])
    try:
        t0 = datetime.fromisoformat(start)
    except ValueError:
        raise ToolError(f"start must be an ISO time like 2026-11-17T10:00, got {start!r}")
    if t0 <= datetime.now():
        raise ToolError("start must be in the future")
    hold = Hold(hold_id=f"hold-{uuid.uuid4().hex[:8]}", start=t0.isoformat(timespec="minutes"),
                end=(t0 + timedelta(minutes=duration_min)).isoformat(timespec="minutes"), title=title)
    d["holds"][idempotency_key] = hold.model_dump()
    _save(d)
    return hold


@mcp.tool(annotations=READ)
@traced_tool("workspace")
def list_holds() -> HoldList:
    """All tentative holds on the calendar."""
    return HoldList(holds=[Hold(**h) for h in _load()["holds"].values()])


@mcp.tool(annotations=WRITE)
@traced_tool("workspace")
def create_email_draft(
    to: Annotated[str, Field(min_length=3, max_length=200)],
    subject: Annotated[str, Field(min_length=1, max_length=200)],
    body: Annotated[str, Field(min_length=1, max_length=5000)],
    idempotency_key: Annotated[str, Field(min_length=8, max_length=100)],
) -> EmailDraft:
    """Save an email DRAFT (never sent). Same idempotency_key returns the same draft."""
    d = _load()
    if idempotency_key not in d["drafts"]:
        d["drafts"][idempotency_key] = EmailDraft(draft_id=f"mail-{uuid.uuid4().hex[:8]}", to=to,
                                                   subject=subject, body=body).model_dump()
        _save(d)
    return EmailDraft(**d["drafts"][idempotency_key])


if __name__ == "__main__":
    setup_tracing("gigbid-mcp-workspace")
    mcp.run()
