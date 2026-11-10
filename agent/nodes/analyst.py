"""Job Analyst: job post -> JobSpec (LLM, small model; rule fallback)."""
import re

from agent.handoffs import JobSpec
from agent.llm import structured
from agent.nodes.common import fence, prompt, trace


def _rules(job: dict) -> JobSpec:
    sents = [s.strip() for s in re.split(r"[.\n]+", job.get("description", "")) if len(s.strip()) > 15]
    deliverables = [s for s in sents if re.search(r"\b(build|create|develop|design|fix|implement|set up|write)\b", s, re.I)]
    reqs = list(dict.fromkeys(job.get("skills", [])[:6] + deliverables[:4]))
    return JobSpec(job_id=job["job_id"], title=job["title"], deliverables=deliverables[:5], requirements=reqs[:8],
                   skills=job.get("skills", []), budget_type=job.get("budget_type", "fixed"),
                   budget_min=job.get("budget_min"), budget_max=job.get("budget_max"),
                   screening_questions=job.get("screening_questions", []))


async def analyst(state, config=None):
    job = state["job"]
    user = (f"job_id: {job['job_id']}\nskills: {job.get('skills')}\nbudget: {job.get('budget_type')} "
            f"{job.get('budget_min')}-{job.get('budget_max')}\nscreening_questions: {job.get('screening_questions')}\n\n"
            f"{fence(job)}")
    spec, info = await structured("analyst", JobSpec, prompt("analyst"), user, lambda: _rules(job))
    spec.job_id = job["job_id"]
    return {"job_spec": spec.model_dump(), "tokens": info["tokens"],
            "trace": [trace("analyst", requirements=len(spec.requirements), **info)]}
