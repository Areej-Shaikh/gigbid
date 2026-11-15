"""Claim splitting and grounding (B3), shared by the Claim Verifier node, the proposal studio's paragraph
regeneration and the evaluations.

- split_claims(): which sentences of a draft make a claim (they cite [evidence_id] or say "I built / we reduced /
  N years ...").
- check_claim(): is the claim grounded in the evidence it cites? Unsupported when it has no citation, cites an
  unknown id, uses a number that is not in the cited text, or shares too few content words with it.
The LLM grader in agent/nodes/verifier.py may refine a check, but never rescues a claim this module failed for a
missing citation, an unknown id or a wrong number.
"""
import re

from agent.handoffs import ClaimCheck

CITE = re.compile(r"\[([A-Za-z0-9_\-]+)\]")

# a sentence is an experience CLAIM if "I/we" is followed by past-tense work or "experience/years"
CLAIM = re.compile(r"\b(i|i've|i have|we)\b[^\"]*\b(built|developed|created|delivered|designed|worked|"
                   r"experience|years|improved|reduced|increased|led|shipped|deployed|automated|raised)\b", re.I)
STOP = set("the a an and or for with from that this into over your our was were have has had are is to of in on at by "
           "which who what when where while about than then them they their there these those using used".split())


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip()) if s.strip()]


def split_claims(text: str) -> list[str]:
    """Sentences that claim experience or results (quoted job text is ignored)."""
    return [s for s in sentences(text) if CITE.search(s) or CLAIM.search(re.sub(r'"[^"]*"', "", s))]


def _content(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9+#]+", s.lower()) if len(w) > 3 and w not in STOP}


def check_claim(claim: str, ids: list[str], pool: dict) -> ClaimCheck:
    """Lexical grounding check of one claim against the evidence items it cites (pool: evidence_id -> item)."""
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


def remove_claims(text: str, bad: set[str]) -> str:
    return " ".join(s for s in sentences(text) if s not in bad)
