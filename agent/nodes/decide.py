"""Decision node: bid / watch / skip, with reasons. Pure rules from config (explainable)."""
from agent.config import cfg
from agent.handoffs import BidDecision
from agent.nodes.common import budget_exceeded, trace


async def decide(state, config=None):
    c, job, risk, fit = cfg(), state["job"], state["risk"], state["fit"]
    d, u = c["decision"], c["user"]
    reasons, action = [], "bid"
    scam = [f for f in risk["flags"] if f in d["scam_flags"]]
    if risk["level"] == "high" or scam:
        action = "skip"; reasons.append(f"risk {risk['level']}: {', '.join(scam or risk['flags'])}")
    if fit["fit_score"] < d["watch_fit"]:
        action = "skip"; reasons.append(f"fit {fit['fit_score']} below {d['watch_fit']}")
    elif fit["fit_score"] < d["min_fit"] and action == "bid":
        action = "watch"; reasons.append(f"fit {fit['fit_score']} is borderline")
    if job.get("budget_type") == "hourly" and job.get("budget_max") and job["budget_max"] < u["min_hourly_rate"]:
        action = "skip"; reasons.append(f"max ${job['budget_max']}/hr is below your floor ${u['min_hourly_rate']}/hr")
    if job.get("budget_type") == "fixed" and job.get("budget_max") and job["budget_max"] < u["min_fixed_budget"]:
        action = "skip"; reasons.append(f"budget ${job['budget_max']} is below your minimum ${u['min_fixed_budget']}")
    if job.get("connects_cost", 0) > u["weekly_connects_budget"]:
        action = "skip"; reasons.append("Connects cost is above your weekly budget")
    if risk["level"] == "medium" and action == "bid":
        action = "watch"; reasons.append("medium risk: review manually")
    if action == "bid":
        reasons.append(f"fit {fit['fit_score']}, risk {risk['level']}")
    decision = BidDecision(action=action, reasons=reasons)
    status = {"bid": "running", "watch": "watch", "skip": "skipped"}[action]
    if budget_exceeded(state):
        status = "needs_attention"
    return {"decision": decision.model_dump(), "status": status, "trace": [trace("decide", action=action, reasons=reasons)]}
