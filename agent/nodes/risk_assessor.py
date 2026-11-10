"""Risk Assessor: client quality + scam / off-platform / prompt-injection flags.
Rule-based on purpose: cheap, explainable, and the rules live in config.yaml."""
import re

from agent.config import cfg
from agent.handoffs import RiskReport
from agent.nodes.common import trace


async def risk_assessor(state, config=None):
    job, client, rc = state["job"], state.get("client") or {}, cfg()["risk"]
    text = f"{job.get('title', '')}\n{job.get('description', '')}".lower()
    score, flags, reasons = 0.0, [], []
    for rule in rc["rules"]:
        m = re.search(rule["pattern"], text, re.I | re.M)
        if m:
            score += rule["weight"]
            flags.append(rule["flag"])
            reasons.append(f"{rule['flag']}: matched \"{m.group(0)}\"")
    c = rc["client"]
    if not client.get("payment_verified"):
        score += c["payment_unverified"]; flags.append("payment_unverified"); reasons.append("client payment not verified")
    if not client.get("total_spent") and not client.get("hires"):
        score += c["no_history"]; flags.append("no_client_history"); reasons.append("client has $0 spent and no hires")
    if client.get("avg_rating") is not None and client["avg_rating"] < c["low_rating_below"]:
        score += c["low_rating"]; flags.append("low_rating"); reasons.append(f"client rating {client['avg_rating']}")
    if job.get("budget_type") == "fixed" and not job.get("budget_max"):
        score += c["zero_budget"]; flags.append("zero_budget"); reasons.append("fixed budget is $0")
    score = min(score, 1.0)
    level = "high" if score >= rc["high"] else "medium" if score >= rc["medium"] else "low"
    summary = (f"verified={client.get('payment_verified')}, spent=${client.get('total_spent', 0):,.0f}, "
               f"hires={client.get('hires', 0)}, rating={client.get('avg_rating')}")
    report = RiskReport(level=level, score=round(score, 2), flags=flags, reasons=reasons, client_summary=summary)
    return {"risk": report.model_dump(), "trace": [trace("risk", level=level, flags=flags)]}
