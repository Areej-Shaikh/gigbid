"""Portfolio tools (A1): search_evidence, get_case_study, list_skills. Read-only."""
from typing import Annotated

from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field

from agent.tracing import traced_tool
from mcp_servers.portfolio.core import READ, CaseStudy, Evidence, EvidenceResults, EvidenceType, SkillCount, SkillList, mcp, store


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
