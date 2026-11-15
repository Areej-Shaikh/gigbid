"""Shared core of the Portfolio MCP server: the FastMCP app, the per-persona evidence index and the result models.
tools.py, resources.py and prompts.py register on `mcp`; server.py is the entry point."""
import os
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from agent.tracing import mcp_request_meta
from rag.ingest.portfolio_loader import load_portfolio, load_profile, portfolio_version
from rag.retriever import build_retriever

mcp = FastMCP("gigbid-portfolio")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
EvidenceType = Literal["cv", "case_study", "repo", "review", "proposal"]

_cache: dict[str, dict] = {}


def store() -> dict:
    """The current persona's index. Persona = the caller's onboarding choice (MCP request _meta "gigbid_persona"),
    else PORTFOLIO_PERSONA. One cached index per persona, rebuilt when any of its files is added or edited (B1)."""
    persona = mcp_request_meta().get("gigbid_persona") or os.getenv("PORTFOLIO_PERSONA", "ai_ml_engineer")
    if "/" in persona or "\\" in persona or persona.startswith("."):
        raise ToolError("invalid persona")
    version = portfolio_version(persona)
    s = _cache.get(persona)
    if s is None or s["version"] != version:
        items = load_portfolio(persona)
        s = _cache[persona] = dict(persona=persona, version=version, items=items, by_id={i["evidence_id"]: i for i in items},
                                   retriever=build_retriever(items), profile=load_profile(persona))
    return s


# ---------------------------------------------------------------- models
class Evidence(BaseModel):
    evidence_id: str
    type: str
    title: str
    snippet: str = Field(description="First 400 characters; load the full item with get_case_study or a resource")
    project: str
    skills: list[str]
    date: str
    client_industry: str
    outcome: str = Field(description="delivered / won / replied / ignored / N stars")
    source: str
    score: float


class EvidenceResults(BaseModel):
    requirement: str
    results: list[Evidence]
    retriever: str


class CaseStudy(BaseModel):
    evidence_id: str
    title: str
    project: str
    skills: list[str]
    date: str
    client_industry: str
    text: str
    source: str


class SkillCount(BaseModel):
    skill: str
    evidence_count: int


class SkillList(BaseModel):
    persona: str
    headline: str
    hourly_rate: float
    skills: list[SkillCount]

