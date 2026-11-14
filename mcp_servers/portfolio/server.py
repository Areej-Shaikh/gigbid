"""Portfolio MCP server (Part A1): READ-ONLY access to one freelancer's portfolio evidence.

Good enough to plug into Claude Desktop or Cursor on its own.

Run:  python -m mcp_servers.portfolio.server          (stdio)
Env:  PORTFOLIO_PERSONA = ai_ml_engineer | fullstack_developer | data_analyst
      RAG_VARIANT       = retriever to use (see rag/retriever.py)
"""
import os
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from agent.tracing import setup_tracing, traced_tool
from rag.ingest.portfolio_loader import load_portfolio, load_profile
from rag.retriever import build_retriever

mcp = FastMCP("gigbid-portfolio")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
EvidenceType = Literal["cv", "case_study", "repo", "review", "proposal"]

_state: dict = {}


def store() -> dict:
    """Load the persona once (lazy), so tests can switch persona via env."""
    persona = os.getenv("PORTFOLIO_PERSONA", "ai_ml_engineer")
    if _state.get("persona") != persona:
        items = load_portfolio(persona)
        _state.update(persona=persona, items=items, by_id={i["evidence_id"]: i for i in items},
                      retriever=build_retriever(items), profile=load_profile(persona))
    return _state


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


# ---------------------------------------------------------------- tools
@mcp.tool(annotations=READ)
@traced_tool("portfolio")
def search_evidence(
    requirement: Annotated[str, Field(min_length=2, max_length=500,
                                      description="One job requirement, e.g. 'RAG chatbot with citations'")],
    k: Annotated[int, Field(ge=1, le=20)] = 5,
    types: Annotated[list[EvidenceType] | None, Field(description="Only these evidence types")] = None,
    outcomes: Annotated[list[str] | None, Field(description="e.g. ['won','replied'] for past proposals")] = None,
    since: Annotated[str | None, Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")] = None,
) -> EvidenceResults:
    """Find portfolio evidence (case studies, repos, reviews, past proposals, CV) that proves a requirement.
    Every claim in a proposal must cite an evidence_id returned here."""
    s = store()
    hits = s["retriever"].search(requirement, k, {"types": types, "outcomes": outcomes, "since": since})
    return EvidenceResults(requirement=requirement, retriever=s["retriever"].name, results=[
        Evidence(**{f: i[f] for f in ("evidence_id", "type", "title", "project", "skills", "date",
                                      "client_industry", "outcome", "source")},
                 snippet=i["text"][:400], score=round(score, 3)) for i, score in hits])


@mcp.tool(annotations=READ)
@traced_tool("portfolio")
def get_case_study(evidence_id: Annotated[str, Field(min_length=1, max_length=100)]) -> CaseStudy:
    """Get the full text of one case study (or any evidence item) by id."""
    i = store()["by_id"].get(evidence_id)
    if not i:
        raise ToolError(f"not_found: {evidence_id}")
    return CaseStudy(**{f: i[f] for f in ("evidence_id", "title", "project", "skills", "date",
                                          "client_industry", "text", "source")})


@mcp.tool(annotations=READ)
@traced_tool("portfolio")
def list_skills() -> SkillList:
    """List the freelancer's skills and how many evidence items support each one."""
    s = store()
    counts = {sk: 0 for sk in s["profile"]["skills"]}
    for i in s["items"]:
        for sk in i["skills"]:
            if i["type"] != "proposal":
                counts[sk] = counts.get(sk, 0) + 1
    return SkillList(persona=s["persona"], headline=s["profile"]["headline"],
                     hourly_rate=s["profile"]["hourly_rate"],
                     skills=[SkillCount(skill=k, evidence_count=v) for k, v in sorted(counts.items(), key=lambda x: -x[1])])


# ---------------------------------------------------------------- resources
@mcp.resource("portfolio://case/{case_id}", mime_type="text/markdown")
def case_resource(case_id: str) -> str:
    """Full case study as markdown."""
    i = store()["by_id"].get(case_id)
    if not i or i["type"] != "case_study":
        raise ValueError(f"case study {case_id} not found")
    return f"# {i['title']}\n\nSkills: {', '.join(i['skills'])} | {i['date']} | {i['client_industry']}\n\n{i['text']}"


@mcp.resource("portfolio://proposal/{proposal_id}", mime_type="text/markdown")
def proposal_resource(proposal_id: str) -> str:
    """A past proposal with its outcome (won / replied / ignored)."""
    i = store()["by_id"].get(proposal_id)
    if not i or i["type"] != "proposal":
        raise ValueError(f"proposal {proposal_id} not found")
    return f"# {i['title']}\n\nOutcome: **{i['outcome']}** | {i['date']}\n\n{i['text']}"


@mcp.resource("portfolio://profile", mime_type="application/json")
def profile_resource() -> dict:
    """Freelancer profile: headline, rate, minimum budget, skills."""
    return store()["profile"]


# ---------------------------------------------------------------- prompts
@mcp.prompt(title="Answer a screening question from my portfolio")
def answer_screening_question(question: str) -> str:
    return (f"Answer this client screening question in 3-5 sentences, in first person:\n\n\"{question}\"\n\n"
            "First call search_evidence with the question. Use ONLY facts from the returned evidence and cite "
            "each fact as [evidence_id]. If nothing relevant is found, say honestly that you have not done it.")


@mcp.prompt(title="Find my best proof for a job")
def best_proof_for_job(job_description: str) -> str:
    return (f"Job description:\n\n{job_description}\n\nSplit it into separate requirements. For each one call "
            "search_evidence and pick the single strongest evidence item. Return a table: requirement | "
            "evidence_id | why it proves it. Mark requirements with no evidence as GAP.")


if __name__ == "__main__":
    setup_tracing("gigbid-mcp-portfolio")
    mcp.run()
