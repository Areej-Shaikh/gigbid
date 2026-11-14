"""Fit Matcher: map every requirement to portfolio evidence (requirement-to-evidence matrix).
Runs in parallel with the Analyst, so it builds its own requirement list from the job's skills + title."""
from langchain_core.runnables import RunnableConfig

from agent.config import cfg
from agent.handoffs import FitReport, RequirementEvidence
from agent.nodes.common import toolbox, trace


def requirements_for(job: dict) -> list[str]:
    reqs = list(job.get("skills") or [])[:8]
    return reqs or [job["title"]]


async def fit_matcher(state, config: RunnableConfig):
    tb, fc, job = toolbox(config), cfg()["fit"], state["job"]
    matrix, evidence = [], {}
    for req in requirements_for(job):
        res = await tb.call("fit", "search_evidence", requirement=f"{req} {job['title']}",
                            k=fc["evidence_per_requirement"], types=["case_study", "repo", "review", "cv"])
        hits = res["results"]
        top = hits[0]["score"] if hits else 0.0
        lexical = any(req.lower() in (" ".join(h["skills"]) + " " + h["snippet"]).lower() for h in hits)
        thr = fc["min_evidence_score"]
        thr = thr.get(res.get("retriever"), thr.get("default", 0.5)) if isinstance(thr, dict) else thr
        covered = bool(hits) and (lexical or top >= thr)
        matrix.append(RequirementEvidence(requirement=req, evidence_ids=[h["evidence_id"] for h in hits],
                                          best_score=top, covered=covered))
        for h in hits:
            evidence[h["evidence_id"]] = h
    fit = sum(m.covered for m in matrix) / len(matrix)
    gaps = [m.requirement for m in matrix if not m.covered]
    report = FitReport(fit_score=round(fit, 2), matrix=matrix,
                       reasons=[f"{sum(m.covered for m in matrix)}/{len(matrix)} requirements have evidence"]
                       + ([f"no evidence for: {', '.join(gaps)}"] if gaps else []))
    return {"fit": report.model_dump(), "evidence": evidence,
            "trace": [trace("fit", fit=report.fit_score, gaps=gaps, tool_calls=len(matrix))]}
