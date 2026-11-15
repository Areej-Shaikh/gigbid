"""Proposals: the proposal studio's paragraph regeneration, and the list of proposals sent to the marketplace."""
import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agent.config import cfg
from agent.llm import structured
from agent.nodes.common import CITE, fence, prompt, sentences
from agent.nodes.compliance import check
from apps.api.auth.security import User
from apps.api.schemas.models import RegenerateIn, RegenerateOut
from rag.verify import CLAIM
from rag.verify import check_claim as _lexical

router = APIRouter(tags=["proposals"])


@router.get("/proposals")
async def list_proposals(request: Request, user: str = User) -> dict:
    """Proposals sent to the marketplace with their status (submitted / ignored / replied / interview / hired)."""
    return await request.app.state.toolbox.call("api", "list_proposals")


class _Paragraph(BaseModel):
    paragraph: str


def _rule_paragraph(paragraph: str, evidence: dict) -> _Paragraph:
    """No LLM available: replace the paragraph with a claim built from evidence it does not cite yet."""
    used = set(CITE.findall(paragraph))
    for eid, e in evidence.items():
        if eid not in used and e.get("text"):
            first = re.split(r"(?<=[.!?])\s+", e["text"].strip())
            result = next((s for s in first if re.search(r"\d", s)), first[0])[:220].rstrip(".")
            return _Paragraph(paragraph=f"I have done similar work: {e.get('title', eid)}. {result} [{eid}].")
    return _Paragraph(paragraph=paragraph)


@router.post("/runs/{job_id}/regenerate", response_model=RegenerateOut)
async def regenerate_paragraph(job_id: str, body: RegenerateIn, request: Request, user: str = User):
    """Proposal studio: rewrite ONE paragraph of the draft waiting for approval, from the same evidence. The result is
    checked like a fresh draft (unsupported claims dropped, Compliance rules applied) and returned as a suggestion; the
    user accepts it through the normal Edit path, which re-runs Compliance and feeds style memory."""
    m = request.app.state.runs
    s = await m.graph.aget_state(m.conf(job_id, user))
    if not (s.tasks and s.tasks[0].interrupts):
        raise HTTPException(409, "this run is not waiting for approval")
    v = s.values
    evidence = v.get("evidence") or {}
    evidence_lines = "\n".join(f"[{k}] {e.get('title', '')}: {(e.get('text') or e.get('snippet', ''))[:600]}"
                               for k, e in evidence.items())
    user_msg = "\n\n".join(filter(None, [
        fence(v.get("job") or {}),
        f"EVIDENCE (cite these ids only):\n{evidence_lines}",
        f"WHOLE PROPOSAL (for context):\n{(v.get('draft') or {}).get('cover_letter', '')}",
        f"PARAGRAPH TO REWRITE:\n{body.paragraph}",
        f"INSTRUCTION: {body.instruction}" if body.instruction else "",
    ]))
    res, info = await structured("writer", _Paragraph, prompt("regenerate"), user_msg, lambda: _rule_paragraph(body.paragraph, evidence))
    kept = []
    for sent in sentences(res.paragraph):          # same claim rule as the verifier: no uncited / unsupported claims
        ids = CITE.findall(sent)
        if (ids or CLAIM.search(sent)) and _lexical(sent, ids, evidence).status == "unsupported":
            continue
        kept.append(sent)
    text, violations = check(" ".join(kept), cfg()["compliance"]["rules"])
    if not text.strip():
        raise HTTPException(422, "the regenerated paragraph did not pass the claim and policy checks; edit it by hand")
    return RegenerateOut(paragraph=text, model=info["model"], removed_by_compliance=violations)
