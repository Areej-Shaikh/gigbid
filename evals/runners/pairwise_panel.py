"""Blind pairwise human panel (B4): classmates compare two anonymised proposals for the same job.

  python -m evals.runners.pairwise_panel prepare      # writes the rater sheet + the hidden key
  # send evals/datasets/pairwise_panel.csv to 3+ raters; each fills their column with A, B or tie
  python -m evals.runners.pairwise_panel analyse      # win rates, sign test, Fleiss' kappa

Systems compared: the deployed retriever (BM25) vs the highest-recall one (V2 hybrid), the central question of
report section 4: does better retrieval give better proposals? Both drafts come from the full bid graph on the same
dev job (rule-based profile, so the only difference is the evidence the retriever found). Order is randomised per
pair with a fixed seed; the key that says which proposal is which is kept in a separate file raters never see.
"""
import argparse
import asyncio
import csv
import json
import os
import random
from contextlib import AsyncExitStack
from pathlib import Path

from evals.stats import fleiss_kappa, sign_test

SHEET = Path("evals/datasets/pairwise_panel.csv")
KEY = Path("evals/datasets/pairwise_key.json")
OUT = Path("evals/results")
SYSTEMS = ("bm25", "v2_hybrid")
RATERS = ("rater_1", "rater_2", "rater_3")
INSTRUCTIONS = ("For each job, read the post, then both proposals. Which proposal would you, as the client, rather "
                "reply to? Write A, B or tie in your column. Judge specificity to the job, believable proof, clarity and "
                "a clear next step. Do not guess which system wrote which.")


async def drafts(jobs: list[dict], variant: str) -> dict[str, str]:
    os.environ["LLM_PROFILE"] = "fake"
    os.environ["RAG_VARIANT"] = variant
    from agent.config import cfg
    cfg.cache_clear()
    from langgraph.checkpoint.memory import InMemorySaver
    from mcp.shared.memory import create_connected_server_and_client_session

    from agent.graphs.bid_graph import build_bid_graph
    from agent.mcp_client import ToolBox
    from mcp_servers.marketplace import server as market
    from mcp_servers.portfolio import server as portfolio
    portfolio._cache.clear()                     # rebuild the index with this retriever
    out = {}
    async with AsyncExitStack() as st:
        m = await st.enter_async_context(create_connected_server_and_client_session(market.mcp._mcp_server))
        p = await st.enter_async_context(create_connected_server_and_client_session(portfolio.mcp._mcp_server))
        tb = await ToolBox({"marketplace": m, "portfolio": p}).init()
        g = build_bid_graph(InMemorySaver())
        for j in jobs:
            os.environ["PORTFOLIO_PERSONA"] = j["persona"]
            res = await g.ainvoke({"job_id": j["job_id"]}, {"configurable": {"toolbox": tb, "thread_id": f"panel-{variant}-{j['job_id']}"},
                                                             "recursion_limit": 40})
            if "__interrupt__" in res and res["draft"]["cover_letter"].strip():
                out[j["job_id"]] = res["draft"]["cover_letter"]
    return out


def prepare(n: int, force: bool) -> None:
    if SHEET.exists() and not force:
        raise SystemExit(f"{SHEET} exists (it may hold ratings); use --force to overwrite")
    from evals.runners.graph_eval import DEV, setup, stratified
    dev = json.loads(DEV.read_text(encoding="utf-8"))
    candidates = [j for j in stratified(dev, 20) if j["label"] == "bid"]
    setup(dev)
    a = asyncio.run(drafts(candidates, SYSTEMS[0]))
    b = asyncio.run(drafts(candidates, SYSTEMS[1]))
    both = [j for j in candidates if j["job_id"] in a and j["job_id"] in b and a[j["job_id"]] != b[j["job_id"]]]
    rng = random.Random(4016)
    rng.shuffle(both)
    pairs, key = [], {}
    for i, j in enumerate(both[:n], 1):
        pid = f"P{i:02d}"
        flip = rng.random() < 0.5
        first, second = (SYSTEMS[1], SYSTEMS[0]) if flip else SYSTEMS
        letters = {SYSTEMS[0]: a[j["job_id"]], SYSTEMS[1]: b[j["job_id"]]}
        key[pid] = {"A": first, "B": second, "job_id": j["job_id"]}
        pairs.append({"pair_id": pid, "job_title": j["title"], "job_post": j["description"],
                      "proposal_A": letters[first], "proposal_B": letters[second], **{r: "" for r in RATERS}, "notes": ""})
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    with SHEET.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, list(pairs[0].keys()))
        w.writeheader()
        w.writerows(pairs)
    KEY.write_text(json.dumps({"systems": SYSTEMS, "seed": 4016, "instructions": INSTRUCTIONS, "pairs": key}, indent=1), encoding="utf-8")
    print(f"wrote {len(pairs)} pairs to {SHEET} (key in {KEY}; {len(both)} jobs had two different drafts)")


def analyse() -> None:
    key = json.loads(KEY.read_text(encoding="utf-8"))
    rows = list(csv.DictReader(SHEET.open(encoding="utf-8-sig")))
    raters = [r for r in RATERS if all((row.get(r) or "").strip() for row in rows)]
    if len(raters) < 2:
        raise SystemExit("need at least 2 raters who rated every pair (columns rater_1, rater_2, rater_3)")

    def norm(v: str) -> str:
        v = v.strip().lower()
        return "tie" if v.startswith("t") or v in ("=", "same", "equal") else v.upper()[:1]

    a_sys, b_sys = key["systems"]
    votes = {a_sys: 0, b_sys: 0, "tie": 0}
    majority = {a_sys: 0, b_sys: 0, "tie": 0}
    table, ratings = [], []
    for row in rows:
        k = key["pairs"][row["pair_id"]]
        choice = [norm(row[r]) for r in raters]
        ratings.append(choice)
        mapped = [k[c] if c in ("A", "B") else "tie" for c in choice]
        for m in mapped:
            votes[m] += 1
        top = max(set(mapped), key=mapped.count)
        winner = top if mapped.count(top) > len(mapped) / 2 else "tie"
        majority[winner] += 1
        table.append(f"| {row['pair_id']} | {row['job_title'][:45]} | {' / '.join(mapped)} | {winner} |")
    p = sign_test(majority[a_sys], majority[b_sys])
    res = {"raters": len(raters), "pairs": len(rows), "votes": votes, "majority_wins": majority, "sign_test_p": round(p, 4),
           "fleiss_kappa": round(fleiss_kappa(ratings), 3)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pairwise_panel.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    md = [f"### Blind pairwise human panel: {a_sys} vs {b_sys} ({len(rows)} pairs, {len(raters)} raters)", "",
          "| | " + a_sys + " | " + b_sys + " | tie |", "|---|---|---|---|",
          f"| Individual votes | {votes[a_sys]} | {votes[b_sys]} | {votes['tie']} |",
          f"| Majority per pair | {majority[a_sys]} | {majority[b_sys]} | {majority['tie']} |", "",
          f"Sign test on majority wins (ties dropped): p = {p:.3f}. Agreement between raters: Fleiss' kappa = {res['fleiss_kappa']}.", "",
          "| Pair | Job | Votes (decoded) | Majority |", "|---|---|---|---|", *table]
    (OUT / "pairwise_panel_table.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["prepare", "analyse"])
    ap.add_argument("--pairs", type=int, default=15)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    prepare(a.pairs, a.force) if a.step == "prepare" else analyse()


if __name__ == "__main__":
    main()
