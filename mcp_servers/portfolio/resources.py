"""Portfolio resource templates (A1): portfolio://case/{id}, portfolio://proposal/{id}, portfolio://profile."""
from mcp_servers.portfolio.core import mcp, store


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
