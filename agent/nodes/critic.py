"""Critic: grounding, personalisation, length. Can send the draft back to the Writer at most twice."""
from agent.config import cfg
from agent.handoffs import Critique
from agent.llm import structured
from agent.nodes.common import CITE, budget_exceeded, fence, prompt, trace, words


def _rules(state) -> Critique:
    c, draft, job = cfg()["critic"], state["draft"], state["job"]
    text = draft["cover_letter"]
    issues = []
    n = words(text)
    if n < c["min_words"]:
        issues.append(f"too short ({n} words, min {c['min_words']})")
    if n > c["max_words"]:
        issues.append(f"too long ({n} words, max {c['max_words']})")
    cites = len(set(CITE.findall(text)))
    if cites < c["min_citations"]:
        issues.append(f"only {cites} cited evidence items (min {c['min_citations']})")
    if any(g in text.lower()[:160] for g in c["generic_openings"]):
        issues.append("generic opening")
    if len(draft.get("screening_answers", [])) < len(job.get("screening_questions", [])):
        issues.append("not all screening questions answered")
    skills = [s.lower() for s in job.get("skills", [])]
    if skills and not any(s in text.lower() for s in skills):
        issues.append("does not mention any of the client's required skills")
    return Critique(approved=not issues, issues=issues,
                    instructions="; ".join(f"fix: {i}" for i in issues))


async def critic(state, config=None):
    rules = _rules(state)
    user = f"{fence(state['job'])}\n\nSCREENING QUESTIONS: {state['job'].get('screening_questions', [])}\n\nDRAFT:\n{state['draft']}"
    llm, info = await structured("critic", Critique, prompt("critic"), user, lambda: rules)
    use_llm = not info["fallback_used"] and not llm.approved
    issues = list(dict.fromkeys(rules.issues + (llm.issues if use_llm else [])))
    result = Critique(approved=not issues, issues=issues,
                      instructions="; ".join(filter(None, [rules.instructions, llm.instructions if use_llm else ""])))
    revisions = state.get("revisions", 0)
    max_rev = cfg()["budgets"]["max_revisions"]
    send_back = not result.approved and revisions < max_rev
    out = {"critique": result.model_dump(), "tokens": info["tokens"],
           "trace": [trace("critic", approved=result.approved, issues=issues, revision=revisions, send_back=send_back, **info)]}
    if send_back:
        out["revisions"] = revisions + 1
    if budget_exceeded(state):
        out["status"] = "needs_attention"
    return out


def route_after_critic(state) -> str:
    if state.get("status") == "needs_attention":
        return "end"
    c = state["critique"]
    if not c["approved"] and state.get("revisions", 0) <= cfg()["budgets"]["max_revisions"] and \
            state["trace"][-1].get("send_back"):
        return "writer"
    return "compliance"
