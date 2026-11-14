"""Run the FULL bid graph on dev jobs and measure decisions + proposal quality (B4, also used for C).

  python -m evals.runners.graph_eval                      # all dev jobs, LLM profile from .env
  python -m evals.runners.graph_eval --per-persona 10     # smaller (Groq free tier rate limits)

Everything runs in-process: GigSim + both MCP servers (in-memory MCP sessions), the dev jobs are loaded
into GigSim, the graph stops at the approval interrupt (nothing is ever submitted).
Writes evals/results/graph_results.json and graph_table.md
"""
import argparse
import asyncio
import json
import os
import statistics
import time
from contextlib import AsyncExitStack
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

import gigsim.app as gigsim  # noqa: E402
from agent.config import cfg  # noqa: E402
from agent.graphs.bid_graph import build_bid_graph  # noqa: E402
from agent.mcp_client import ToolBox  # noqa: E402
from mcp_servers.marketplace import server as market  # noqa: E402
from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter  # noqa: E402
from mcp_servers.portfolio import server as portfolio  # noqa: E402

DEV = Path("evals/datasets/dev_jobs.json")
GOOD = {"client_id": "dev-good", "payment_verified": True, "total_spent": 8000, "hires": 12, "avg_rating": 4.8, "reviews": 9}
RISKY = {"client_id": "dev-risky", "payment_verified": False, "total_spent": 0, "hires": 0, "avg_rating": None, "reviews": 0}


def setup(jobs):
    gigsim.ERROR_RATE = 0
    gigsim.RATE_LIMIT = 10_000
    gigsim.JOBS = {j["job_id"]: {**j, "client_id": "dev-risky" if j["scam"] else "dev-good", "connects_cost": 8,
                                 "screening_questions": [], "posted_at": "", "country": ""} for j in jobs}
    gigsim.CLIENTS = {"dev-good": GOOD, "dev-risky": RISKY}
    market.RATE_LIMIT_PER_MIN = 10_000
    market.set_marketplace(GigSimAdapter(base_url="http://gigsim", transport=httpx.ASGITransport(app=gigsim.app)))


def f1(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


async def run(jobs, label: str, graph_builder=build_bid_graph) -> list[dict]:
    rows = []
    async with AsyncExitStack() as stack:
        m = await stack.enter_async_context(create_connected_server_and_client_session(market.mcp._mcp_server))
        p = await stack.enter_async_context(create_connected_server_and_client_session(portfolio.mcp._mcp_server))
        tb = await ToolBox({"marketplace": m, "portfolio": p}).init()
        graph = graph_builder(InMemorySaver())
        for n, j in enumerate(jobs):
            os.environ["PORTFOLIO_PERSONA"] = j["persona"]
            t = time.perf_counter()
            out = await graph.ainvoke({"job_id": j["job_id"]},
                                      {"configurable": {"toolbox": tb, "thread_id": f"{label}-{j['job_id']}"},
                                       "recursion_limit": cfg()["budgets"]["max_steps"]})
            secs = time.perf_counter() - t
            action = (out.get("decision") or {}).get("action", "error")
            v = out.get("verification") or {}
            price = (out.get("price") or {}).get("amount")
            band = j.get("fair_price_band")
            rows.append({
                "job_id": j["job_id"], "persona": j["persona"], "style": j["style"], "label": j["label"], "scam": j["scam"],
                "action": action, "flagged_scam": any(f in (out.get("risk") or {}).get("flags", [])
                                                      for f in cfg()["decision"]["scam_flags"]),
                "fit": (out.get("fit") or {}).get("fit_score"), "price": price,
                "price_in_band": (band[0] <= price <= band[1]) if (band and price) else None,
                "claims": len(v.get("checks", [])), "unsupported_before": v.get("unsupported_before"),
                "unsupported_after": v.get("unsupported_after"), "critic_ok": (out.get("critique") or {}).get("approved"),
                "revisions": out.get("revisions", 0), "tokens": out.get("tokens", 0), "seconds": round(secs, 2),
                "fallbacks": sum(1 for t in out.get("trace", []) if t.get("fallback_used")),
                "status": out.get("status"),
            })
            print(f"[{n + 1}/{len(jobs)}] {j['job_id']} {j['style']:9s} label={j['label']:4s} -> {action:5s} "
                  f"fit={rows[-1]['fit']} unsupported={rows[-1]['unsupported_before']} {secs:.1f}s", flush=True)
    return rows


def summary(rows):
    bid = lambda r: r["action"] == "bid"  # noqa: E731  ("watch" counts as not-bid)
    tp = sum(bid(r) and r["label"] == "bid" for r in rows)
    fp = sum(bid(r) and r["label"] == "skip" for r in rows)
    fn = sum(not bid(r) and r["label"] == "bid" for r in rows)
    sp, sr, _ = f1(sum(r["flagged_scam"] and r["scam"] for r in rows), sum(r["flagged_scam"] and not r["scam"] for r in rows),
                   sum(not r["flagged_scam"] and r["scam"] for r in rows))
    drafted = [r for r in rows if r["claims"]]
    secs = sorted(r["seconds"] for r in rows)
    priced = [r for r in rows if r["price_in_band"] is not None]
    return {
        "jobs": len(rows), "bid_precision": round(f1(tp, fp, fn)[0], 3), "bid_recall": round(f1(tp, fp, fn)[1], 3),
        "bid_f1": round(f1(tp, fp, fn)[2], 3), "scam_precision": round(sp, 3), "scam_recall": round(sr, 3),
        "price_in_fair_band": round(sum(r["price_in_band"] for r in priced) / len(priced), 3) if priced else None,
        "proposals_drafted": len(drafted),
        "unsupported_claims_per_proposal_before": round(statistics.mean(r["unsupported_before"] for r in drafted), 3) if drafted else None,
        "unsupported_claims_per_proposal_after": round(statistics.mean(r["unsupported_after"] for r in drafted), 3) if drafted else None,
        "critic_approved_rate": round(sum(bool(r["critic_ok"]) for r in drafted) / len(drafted), 3) if drafted else None,
        "avg_tokens_per_job": round(statistics.mean(r["tokens"] for r in rows), 1),
        "p50_s": round(statistics.median(secs), 2), "p95_s": round(statistics.quantiles(secs, n=20)[18], 2) if len(secs) > 1 else secs[0],
        "llm_fallbacks": sum(r["fallbacks"] for r in rows),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=0, help="limit jobs per persona (0 = all)")
    ap.add_argument("--name", default="graph")
    a = ap.parse_args()
    jobs = json.loads(DEV.read_text(encoding="utf-8"))
    if a.per_persona:
        jobs = [j for p in sorted({x["persona"] for x in jobs}) for j in [x for x in jobs if x["persona"] == p][: a.per_persona]]
    setup(jobs)
    c = cfg()
    tag = f"LLM profile={c['profile']}; RAG_VARIANT={os.getenv('RAG_VARIANT', 'bm25')}"
    rows = asyncio.run(run(jobs, a.name))
    s = summary(rows)
    out = Path("evals/results")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{a.name}_results.json").write_text(json.dumps({"tag": tag, "summary": s, "rows": rows}, indent=1), encoding="utf-8")
    md = [f"### Bid graph on dev set ({tag})", "", "| Metric | Value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in s.items()]
    (out / f"{a.name}_table.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
