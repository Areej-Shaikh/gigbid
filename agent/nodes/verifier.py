"""Claim verification (B3): split the draft into claims, check each against the cited evidence,
remove unsupported claims BEFORE the Critic sees the draft. Splitting and the grounding check live in rag/verify.py;
this node adds an LLM grader that may refine (never rescue) the lexical verdicts."""

from pydantic import BaseModel

from agent.handoffs import ClaimCheck, VerificationReport
from agent.llm import structured
from agent.nodes.common import prompt, trace
from agent.security import on
from rag.verify import CITE, CLAIM, split_claims
from rag.verify import check_claim as _lexical
from rag.verify import remove_claims as _clean

__all__ = ["verifier", "CLAIM", "_lexical"]


class _LLMChecks(BaseModel):
    checks: list[ClaimCheck]


async def verifier(state, config=None):
    draft, pool = state["draft"], state.get("evidence") or {}
    if not on("claim_verifier"):                  # evaluation only: defence layer switched off
        return {"verification": VerificationReport(checks=[], unsupported_before=0, unsupported_after=0, removed=[]).model_dump(),
                "trace": [trace("verifier", skipped="claim_verifier off")]}
    parts = [draft["cover_letter"]] + draft.get("screening_answers", [])
    claims = [s for p in parts for s in split_claims(p)]   # quoted job text is ignored
    lexical = [_lexical(c, CITE.findall(c), pool) for c in claims]
    checks, info = lexical, {"model": "rules", "tokens": 0}
    if claims:
        user = "\n\n".join(f"CLAIM {n}: {c.claim}\nEVIDENCE: " +
                           " | ".join((pool.get(i) or {}).get("text", "MISSING")[:600] for i in c.evidence_ids)
                           for n, c in enumerate(lexical))
        res, info = await structured("verifier", _LLMChecks, prompt("verifier"), user, lambda: _LLMChecks(checks=lexical))
        if len(res.checks) == len(lexical):
            # never let the LLM "rescue" a claim with no / unknown citation
            checks = [lx if lx.note.startswith(("no citation", "unknown", "number")) else r for lx, r in zip(lexical, res.checks)]
    bad = {c.claim for c in checks if c.status == "unsupported"}
    cleaned = {"cover_letter": _clean(draft["cover_letter"], bad),
               "screening_answers": [_clean(a, bad) or "I would rather discuss this on a short call." for a in draft.get("screening_answers", [])]}
    report = VerificationReport(checks=checks, unsupported_before=len(bad), unsupported_after=0, removed=sorted(bad))
    return {"draft": cleaned, "verification": report.model_dump(), "tokens": info.get("tokens", 0),
            "trace": [trace("verifier", claims=len(claims), unsupported_removed=len(bad), model=info.get("model"))]}
