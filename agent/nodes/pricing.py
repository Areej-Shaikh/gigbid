"""Pricing Strategist: bid from market stats, client spend and the user's floor; is the Connects cost worth it?"""
import statistics

from langchain_core.runnables import RunnableConfig

from agent.config import cfg
from agent.handoffs import PriceQuote
from agent.nodes.common import toolbox, trace


async def pricing(state, config: RunnableConfig):
    tb, c, job, client = toolbox(config), cfg(), state["job"], state.get("client") or {}
    btype = job.get("budget_type", "fixed")
    pos = c["pricing"]["market_position"]
    market, used = [], []
    for skill in (job.get("skills") or [])[:3]:
        s = await tb.call("pricing", "get_price_stats", skill=skill)
        if s.get("found") and s.get(btype):
            market.append(s[btype][pos]); used.append(skill)
    rationale = []
    floor = c["user"]["min_hourly_rate"] if btype == "hourly" else c["user"]["min_fixed_budget"]
    if market:
        amount = statistics.median(market)
        rationale.append(f"market {pos} for {', '.join(used)}: ${amount:,.0f}{'/hr' if btype == 'hourly' else ''}")
    else:
        amount = job.get("budget_max") or floor
        rationale.append("no market data for these skills; started from the client's budget")
    if client.get("total_spent", 0) > c["pricing"]["big_spender_usd"]:
        amount *= 1.10; rationale.append("+10%: client has spent a lot and pays for quality")
    elif not client.get("hires"):
        amount *= 1 - c["pricing"]["new_client_discount"]; rationale.append("small discount: new client")
    if job.get("budget_max"):
        amount = min(amount, job["budget_max"]); rationale.append(f"capped at client max ${job['budget_max']:,.0f}")
    if job.get("budget_min") and amount < job["budget_min"]:
        amount = job["budget_min"]; rationale.append(f"raised to client min ${job['budget_min']:,.0f}")
    if amount < floor:
        amount = floor; rationale.append(f"raised to your floor ${floor}")
    balance = (await tb.call("pricing", "get_connects_balance"))["balance"]
    cost = job.get("connects_cost", 0)
    worth = cost <= balance and state["fit"]["fit_score"] >= c["decision"]["min_fit"]
    rationale.append(f"{cost} Connects of {balance} left: {'worth it' if worth else 'NOT worth it'}")
    q = PriceQuote(amount=round(amount, 2), budget_type=btype, rationale=rationale,
                   market={"skills": used, "position": pos}, connects_cost=cost, connects_balance=balance,
                   connects_worth_it=worth)
    return {"price": q.model_dump(), "trace": [trace("pricing", amount=q.amount, connects_worth_it=worth)]}
