"""R&D question C: is the multi-agent design worth it?

  python -m evals.runners.architecture_eval --models openai/gpt-oss-20b            # 50 stratified dev jobs
  python -m evals.runners.architecture_eval --models openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b
  python -m evals.runners.architecture_eval --resume                               # continue after a quota stop

Compares, on the SAME jobs with the SAME model for every LLM call:
  (a) react       one ReAct agent holding all read tools (langgraph.prebuilt.create_react_agent)
  (b) supervisor  prebuilt supervisor (langgraph-supervisor) with a research agent and a writer agent
  (c) graph       GigBid's hand-built bid graph (parallel analysis, verifier, critic, compliance)

Every architecture gets the same MCP servers (in-memory sessions) and is scored by the same functions on
what would reach the human at the approval step:
  decision accuracy and bid F1 vs gold labels | unsupported claims in the final letter (the claim verifier's
  citation check) | policy violations still in the final letter (Compliance rules + price floor) |
  simulated client reaction in GigSim | tokens | latency.
Jobs run in job-major order (graph, react, supervisor on one job, then the next), so a run stopped by a daily
token limit is still a paired comparison. Writes evals/results/architecture_results.json and _table.md.
"""
import argparse
import asyncio
import json
import logging
import math
import os
import statistics
import time
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import AIMessage  # noqa: E402
from langchain_mcp_adapters.tools import load_mcp_tools  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.prebuilt import create_react_agent  # noqa: E402
from langgraph_supervisor import create_supervisor  # noqa: E402
from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import gigsim.app as gigsim  # noqa: E402
from agent.config import cfg  # noqa: E402
from agent.graphs.bid_graph import build_bid_graph  # noqa: E402
from agent.mcp_client import ToolBox  # noqa: E402
from agent.nodes.common import CITE, prompt, sentences  # noqa: E402
from agent.nodes.compliance import check  # noqa: E402
from agent.nodes.verifier import CLAIM, _lexical  # noqa: E402
from evals.runners.graph_eval import DEV, f1, setup, stratified  # noqa: E402
from mcp_servers.marketplace import server as market  # noqa: E402
from mcp_servers.portfolio import server as portfolio  # noqa: E402
from rag.ingest.portfolio_loader import load_portfolio  # noqa: E402

OUT = Path("evals/results")
ARCHS = ("graph", "react", "supervisor")
REACT_TOOLS = {"get_job", "get_client_history", "list_skills", "search_evidence", "get_case_study",
               "get_price_stats", "get_connects_balance"}
RESEARCH_TOOLS = {"get_job", "get_client_history", "list_skills", "search_evidence", "get_price_stats"}
WRITER_TOOLS = {"search_evidence", "get_case_study"}


class Decision(BaseModel):
    action: Literal["bid", "skip", "watch"]
    reasons: list[str] = Field(default_factory=list)
    price: float | None = None
    cover_letter: str = ""


class DailyLimit(RuntimeError):
    pass


def _daily(e: BaseException | str) -> bool:
    s = str(e)
    return "429" in s and ("per day" in s or "(TPD)" in s or "(RPD)" in s)


# ---------------------------------------------------------------- shared scoring
_pools: dict[str, dict] = {}


def pool(persona: str) -> dict:
    if persona not in _pools:
        _pools[persona] = {i["evidence_id"]: i for i in load_portfolio(persona)}
    return _pools[persona]


def score_letter(letter: str, price: float | None, job: dict, persona: str) -> dict:
    claims = [s for s in sentences(letter) if CITE.search(s) or CLAIM.search(s)]
    checks = [_lexical(c, CITE.findall(c), pool(persona)) for c in claims]
    violations = len(check(letter, cfg()["compliance"]["rules"])[1]) if letter else 0
    u = cfg()["user"]
    floor = u["min_hourly_rate"] if job.get("budget_type") == "hourly" else u["min_fixed_budget"]
    below = bool(price is not None and price < floor)
    return {"claims": len(claims), "unsupported": sum(c.status == "unsupported" for c in checks),
            "violations_in_letter": violations + below, "price_below_floor": below}


def client_reaction(letter: str, price: float | None, job_id: str) -> str:
    """SIMULATION: the same GigSim client logic the real submit path uses (deterministic per job + letter)."""
    proposal = {"cover_letter": letter, "bid_amount": price or 0, "status": "submitted"}
    gigsim.client_reacts(proposal, gigsim.JOBS[job_id])
    return proposal["status"]


def tokens_of(messages) -> int:
    return sum((m.usage_metadata or {}).get("total_tokens", 0) for m in messages
               if isinstance(m, AIMessage) and getattr(m, "usage_metadata", None))


# ---------------------------------------------------------------- the three architectures
async def run_graph(graph, tb, job_id: str) -> dict:
    conf = {"configurable": {"toolbox": tb, "thread_id": f"arch-{job_id}", "user_id": "arch"},
            "recursion_limit": cfg()["budgets"]["max_steps"]}
    out = await graph.ainvoke({"job_id": job_id}, conf)
    fb = [t for t in out.get("trace", []) if t.get("fallback_used")]
    if any(_daily(t.get("error") or "") for t in fb):
        raise DailyLimit(next(t["error"] for t in fb if _daily(t.get("error") or "")))
    latest = {t["node"]: t for t in out.get("trace", []) if "fallback_used" in t}
    draft = out.get("draft") or {}
    return {"action": (out.get("decision") or {}).get("action", "error"),
            "letter": draft.get("cover_letter", "") if "__interrupt__" in out else "",
            "price": (out.get("price") or {}).get("amount"), "tokens": out.get("tokens", 0),
            "caught_by_guard": len((out.get("compliance") or {}).get("violations", [])),
            "unsupported_removed": (out.get("verification") or {}).get("unsupported_before", 0),
            "valid": not any(t["fallback_used"] for t in latest.values())}


async def run_agent(agent, job_id: str) -> dict:
    res = await agent.ainvoke({"messages": [("user", f"Job id: {job_id}. Decide whether to bid; if you bid, write the proposal.")]},
                              {"recursion_limit": 40})
    d: Decision = res["structured_response"]
    return {"action": d.action, "letter": d.cover_letter if d.action == "bid" else "", "price": d.price,
            "tokens": tokens_of(res["messages"]), "caught_by_guard": 0, "unsupported_removed": 0, "valid": True}


def build_agents(model: ChatOpenAI, tools: list) -> dict:
    by = {t.name: t for t in tools}
    react = create_react_agent(model, [by[n] for n in sorted(REACT_TOOLS)], prompt=prompt("baseline_react"),
                               response_format=Decision)
    research = create_react_agent(model, [by[n] for n in sorted(RESEARCH_TOOLS)], prompt=prompt("baseline_research"),
                                  name="research_agent")
    writer = create_react_agent(model, [by[n] for n in sorted(WRITER_TOOLS)], prompt=prompt("baseline_writer"),
                                name="writer_agent")
    sup = create_supervisor([research, writer], model=model, prompt=prompt("baseline_supervisor"),
                            response_format=Decision).compile()
    return {"react": react, "supervisor": sup}


# ---------------------------------------------------------------- runner
async def run(jobs: list[dict], model_names: list[str], done: list[dict], save) -> tuple[list[dict], str | None]:
    """Job n uses model_names[n % k] for EVERY LLM call of all three architectures (a fair, paired comparison per
    job); spreading jobs over several models multiplies throughput under per-model daily quotas. A model that hits
    its daily limit is skipped for the rest of the run; the run stops when all are exhausted (resume later)."""
    p = cfg()["profiles"][cfg()["profile"]]
    rows, finished = list(done), {(r["arch"], r["job_id"]) for r in done}
    exhausted: dict[str, str] = {}
    async with AsyncExitStack() as stack:
        m = await stack.enter_async_context(create_connected_server_and_client_session(market.mcp._mcp_server))
        ps = await stack.enter_async_context(create_connected_server_and_client_session(portfolio.mcp._mcp_server))
        tb = await ToolBox({"marketplace": m, "portfolio": ps}).init()
        tools = await load_mcp_tools(m) + await load_mcp_tools(ps)
        agents_by_model = {name: build_agents(ChatOpenAI(model=name, base_url=p["base_url"], api_key=os.getenv(p["api_key_env"]),
                                                         temperature=cfg()["temperature"], timeout=120, max_retries=6), tools)
                           for name in model_names}
        graph = build_bid_graph(InMemorySaver())
        for n, j in enumerate(jobs):
            model_name = model_names[n % len(model_names)]
            if model_name in exhausted:
                if len(exhausted) == len(model_names):
                    return rows, next(iter(exhausted.values()))
                continue
            for size in ("small", "strong", "fallback"):      # the graph uses the same single model as the baselines
                p["models"][size] = model_name
            agents = agents_by_model[model_name]
            os.environ["PORTFOLIO_PERSONA"] = j["persona"]
            for arch in ARCHS:
                if (arch, j["job_id"]) in finished:
                    continue
                t0 = time.perf_counter()
                try:
                    r = await (run_graph(graph, tb, j["job_id"]) if arch == "graph" else run_agent(agents[arch], j["job_id"]))
                except Exception as e:  # noqa: BLE001 - one failed run must not stop the comparison
                    if isinstance(e, DailyLimit) or _daily(e):
                        exhausted[model_name] = str(e)[:300]
                        print(f"  {model_name}: daily limit reached, skipping it for now", flush=True)
                        break
                    r = {"action": "error", "letter": "", "price": None, "tokens": 0, "caught_by_guard": 0,
                         "unsupported_removed": 0, "valid": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}
                r["model"] = model_name
                job = gigsim.JOBS[j["job_id"]]
                scored = score_letter(r["letter"], r["price"], job, j["persona"])
                reaction = client_reaction(r["letter"], r["price"], j["job_id"]) if r["action"] == "bid" and r["letter"] else None
                rows.append({"arch": arch, "job_id": j["job_id"], "persona": j["persona"], "style": j["style"],
                             "label": j["label"], "scam": j["scam"], **{k: v for k, v in r.items() if k != "letter"},
                             "letter": r["letter"], **scored, "reaction": reaction,
                             "seconds": round(time.perf_counter() - t0, 1)})
                save(rows)
                print(f"[{n + 1}/{len(jobs)}] {j['job_id']} {j['style']:9s} label={j['label']:4s} {arch:10s} -> "
                      f"{r['action']:5s} unsupported={scored['unsupported']} viol={scored['violations_in_letter']} "
                      f"tok={r['tokens']} {rows[-1]['seconds']}s{'' if r['valid'] else '  [INVALID ' + str(r.get('error', 'fallback'))[:80] + ']'}",
                      flush=True)
    return rows, (next(iter(exhausted.values())) if exhausted else None)   # some jobs left for an exhausted model


# ---------------------------------------------------------------- tables
def summarise(rows: list[dict]) -> dict:
    ok = [r for r in rows if r["valid"]]
    if not ok:
        return {}
    bid = lambda r: r["action"] == "bid"  # noqa: E731
    p, rc, f = f1(sum(bid(r) and r["label"] == "bid" for r in ok), sum(bid(r) and r["label"] == "skip" for r in ok),
                  sum(not bid(r) and r["label"] == "bid" for r in ok))
    drafted = [r for r in ok if r["letter"]]
    sent = [r for r in ok if r["reaction"]]
    secs = sorted(r["seconds"] for r in ok)
    return {
        "valid_runs": len(ok), "accuracy": round(sum(bid(r) == (r["label"] == "bid") for r in ok) / len(ok), 3),
        "bid_precision": round(p, 3), "bid_recall": round(rc, 3), "bid_f1": round(f, 3),
        "scams_bid_on": sum(bid(r) and r["scam"] for r in ok),
        "proposals": len(drafted),
        "unsupported_per_proposal": round(statistics.mean(r["unsupported"] for r in drafted), 2) if drafted else None,
        "violations_reaching_human": sum(r["violations_in_letter"] for r in ok),
        "violations_caught_by_guard": sum(r["caught_by_guard"] for r in ok),
        "reply_rate": round(sum(r["reaction"] != "ignored" for r in sent) / len(sent), 3) if sent else None,
        "avg_tokens": round(statistics.mean(r["tokens"] for r in ok)),
        "p50_s": round(statistics.median(secs), 1),
        "p95_s": round(secs[min(len(secs) - 1, math.ceil(0.95 * len(secs)) - 1)], 1),
    }


def tables(rows: list[dict], tag: str) -> str:
    jobs_all = {r["job_id"] for r in rows}
    paired = {j for j in jobs_all if all(any(r["job_id"] == j and r["arch"] == a and r["valid"] for r in rows) for a in ARCHS)}
    pr = [r for r in rows if r["job_id"] in paired]
    s = {a: summarise([r for r in pr if r["arch"] == a]) for a in ARCHS}
    keys = list(next((v for v in s.values() if v), {}).keys())
    md = [f"### R&D question C: one ReAct agent vs prebuilt supervisor vs hand-built graph ({tag})", "",
          f"Paired comparison on the {len(paired)} jobs where all three architectures produced a valid run "
          f"({len(jobs_all)} jobs attempted). Within each job all three architectures use the same model.", "",
          "| Metric | (a) ReAct agent | (b) Supervisor | (c) GigBid graph |", "|---|---|---|---|"]
    md += [f"| {k} | {s['react'].get(k)} | {s['supervisor'].get(k)} | {s['graph'].get(k)} |" for k in keys]
    md += ["", "**Decision accuracy by job type**", "", "| Job type | n | (a) ReAct | (b) Supervisor | (c) Graph |", "|---|---|---|---|---|"]
    for style in sorted({r["style"] for r in pr}):
        acc = {}
        for a in ARCHS:
            rr = [r for r in pr if r["arch"] == a and r["style"] == style]
            acc[a] = f"{sum((r['action'] == 'bid') == (r['label'] == 'bid') for r in rr)}/{len(rr)}" if rr else "-"
        md.append(f"| {style} | {len({r['job_id'] for r in pr if r['style'] == style})} | {acc['react']} | {acc['supervisor']} | {acc['graph']} |")
    inv = {a: sum(1 for r in rows if r["arch"] == a and not r["valid"]) for a in ARCHS}
    md += ["", f"Invalid runs excluded (provider errors, LLM fallbacks, or no structured answer): {inv}."]
    return "\n".join(md) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="openai/gpt-oss-20b",
                    help="comma-separated; job n uses models[n % k] for all three architectures")
    ap.add_argument("--jobs", type=int, default=50)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--name", default="architecture")
    a = ap.parse_args()
    for noisy in ("httpx", "mcp", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    dev = json.loads(DEV.read_text(encoding="utf-8"))
    jobs = stratified(dev, math.ceil(a.jobs / 3))[: a.jobs]
    setup(dev)
    cfg()["llm_rate_limit_retries"] = 8
    res_file = OUT / f"{a.name}_results.json"
    done = json.loads(res_file.read_text(encoding="utf-8"))["rows"] if a.resume and res_file.exists() else []
    done = [r for r in done if r["valid"]]
    models = [m.strip() for m in a.models.split(",") if m.strip()]
    tag = (f"models={', '.join(models)} (one per job, same for all three architectures) via {cfg()['profile']} profile; "
           f"{len(jobs)} stratified dev jobs; RAG_VARIANT={os.getenv('RAG_VARIANT', 'bm25')}")
    OUT.mkdir(parents=True, exist_ok=True)
    save = lambda rows: res_file.write_text(json.dumps({"tag": tag + " (in progress)", "rows": rows}, indent=1), encoding="utf-8")  # noqa: E731
    rows, stopped = asyncio.run(run(jobs, models, done, save))
    if stopped:
        print(f"STOPPED: daily token limit ({stopped[:160]}). Re-run with --resume later.")
        tag += "; PARTIAL (daily token limit)"
    res_file.write_text(json.dumps({"tag": tag, "rows": rows}, indent=1), encoding="utf-8")
    md = tables(rows, tag)
    (OUT / f"{a.name}_table.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
