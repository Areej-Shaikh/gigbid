"""Claim verification (B3): split the draft into claims, check each against the cited evidence,
remove unsupported claims BEFORE the Critic sees the draft."""
import re

from pydantic import BaseModel

from agent.handoffs import ClaimCheck, VerificationReport
from agent.llm import structured
from agent.nodes.common import CITE, prompt, sentences, trace

# a sentence is an experience CLAIM if "I/we" is followed by past-tense work or "experience/years"
CLAIM = re.compile(r"\b(i|i've|i have|we)\b[^\"]*\b(built|developed|created|delivered|designed|worked|"
                   r"experience|years|improved|reduced|increased|led|shipped|deployed|automated|raised)\b", re.I)
STOP = set("the a an and or for with from that this into over your our was were have has had are is to of in on at by "
           "which who what when where while about than then them they their there these those using used".split())


def _content(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9+#]+", s.lower()) if len(w) > 3 and w not in STOP}


def _lexical(claim: str, ids: list[str], pool: dict) -> ClaimCheck:
    if not ids:
        return ClaimCheck(claim=claim, status="unsupported", note="no citation")
    missing = [i for i in ids if i not in pool]
    if missing:
        return ClaimCheck(claim=claim, evidence_ids=ids, status="unsupported", note=f"unknown evidence {missing}")
    ev = " ".join(pool[i].get("text") or pool[i].get("snippet", "") for i in ids).lower()
    bare = CITE.sub("", claim)
    nums = re.findall(r"\d+(?:\.\d+)?", bare)
    if any(n not in ev for n in nums):
        return ClaimCheck(claim=claim, evidence_ids=ids, status="unsupported", note="number not in evidence")
    words = _content(bare)
    overlap = len([w for w in words if w in ev]) / max(len(words), 1)
    status = "supported" if overlap >= 0.5 else "partial" if overlap >= 0.3 else "unsupported"
    return ClaimCheck(claim=claim, evidence_ids=ids, status=status, note=f"overlap {overlap:.2f}")


class _LLMChecks(BaseModel):
    checks: list[ClaimCheck]


def _clean(text: str, bad: set[str]) -> str:
    return " ".join(s for s in sentences(text) if s not in bad)


async def verifier(state, config=None):
    draft, pool = state["draft"], state.get("evidence") or {}
    parts = [draft["cover_letter"]] + draft.get("screening_answers", [])
    claims = [s for p in parts for s in sentences(p)
              if CITE.search(s) or CLAIM.search(re.sub(r'"[^"]*"', "", s))]   # ignore quoted job text
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
