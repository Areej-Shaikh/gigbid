"""Portfolio prompt templates (A1) a freelancer would pick in their MCP host."""
from mcp_servers.portfolio.core import mcp


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
