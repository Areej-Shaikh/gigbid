"""Compliance Guard: enforce the policy pack (config.yaml -> compliance.rules).
Removes sentences with contact details, off-platform contact/payment, guarantees. Can block."""
import re

from agent.config import cfg
from agent.handoffs import ComplianceVerdict
from agent.nodes.common import sentences, trace


def check(text: str, rules: list[dict]) -> tuple[str, list[str]]:
    kept, violations = [], []
    for s in sentences(text):
        hit = [r["id"] for r in rules if re.search(r["pattern"], s)]
        if hit:
            violations += [f"{h}: \"{s[:80]}\"" for h in hit]
        else:
            kept.append(s)
    return " ".join(kept), violations


async def compliance(state, config=None):
    c = cfg()["compliance"]
    draft = state["draft"]
    letter, v = check(draft["cover_letter"], c["rules"])
    answers = []
    for a in draft.get("screening_answers", []):
        a2, v2 = check(a, c["rules"])
        answers.append(a2); v += v2
    blocked = len(v) > c["block_if_removed_more_than"] or not letter.strip()
    verdict = ComplianceVerdict(passed=not v, blocked=blocked, violations=v, cover_letter=letter, screening_answers=answers)
    out = {"compliance": verdict.model_dump(), "draft": {"cover_letter": letter, "screening_answers": answers},
           "trace": [trace("compliance", violations=len(v), blocked=blocked)]}
    if blocked:
        out["status"] = "needs_attention"
        out["errors"] = ["compliance blocked the draft: " + "; ".join(v[:3])]
    return out
