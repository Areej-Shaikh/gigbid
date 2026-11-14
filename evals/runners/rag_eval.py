"""Compare retrieval variants on the dev set (B4 retrieval metrics). One command reruns everything.

  python -m evals.runners.rag_eval                       # all variants, real open models
  python -m evals.runners.rag_eval --variants bm25 v0_naive v3_rerank
  python -m evals.runners.rag_eval --embedder hash --reranker overlap   # offline smoke test ONLY

Writes evals/results/rag_results.json (per job), rag_summary.csv and rag_table.md.
Metrics per job (in-niche jobs with gold evidence):
  Recall@5 = gold items in top 5 / min(5, #gold)     MRR = 1 / rank of first gold item
  nDCG@10  = graded (case study 2, repo/review 1)
Off-niche jobs (no gold): "false evidence rate" = share where the retriever still returns evidence.
"""
import argparse
import csv
import json
import math
import statistics
import time
from collections import defaultdict
from pathlib import Path

from agent.config import cfg
from rag.ingest.portfolio_loader import load_portfolio
from rag.retriever import VARIANTS, build_retriever

DEV = Path("evals/datasets/dev_jobs.json")
OUT = Path("evals/results")
EVIDENCE_TYPES = {"types": ["case_study", "repo", "review", "cv"]}


def metrics(ranked_ids: list[str], gold: dict[str, int]) -> dict:
    top5 = ranked_ids[:5]
    rec = len([i for i in top5 if i in gold]) / min(5, len(gold))
    mrr = next((1 / (r + 1) for r, i in enumerate(ranked_ids[:10]) if i in gold), 0.0)
    dcg = sum((2 ** gold.get(i, 0) - 1) / math.log2(r + 2) for r, i in enumerate(ranked_ids[:10]))
    ideal = sorted(gold.values(), reverse=True)[:10]
    idcg = sum((2 ** g - 1) / math.log2(r + 2) for r, g in enumerate(ideal))
    return {"recall@5": rec, "mrr": mrr, "ndcg@10": dcg / idcg if idcg else 0.0}


def p95(xs):
    return statistics.quantiles(xs, n=20)[18] if len(xs) >= 2 else (xs[0] if xs else 0)


def run(variants: list[str], overrides: dict, tag: str) -> list[dict]:
    jobs = json.loads(DEV.read_text(encoding="utf-8"))
    rows = []
    for persona in sorted({j["persona"] for j in jobs}):
        items = load_portfolio(persona)
        pj = [j for j in jobs if j["persona"] == persona and j["style"] != "scam"]
        for v in variants:
            t0 = time.time()
            r = build_retriever(items, v, **({} if v == "bm25" else overrides))
            print(f"  {persona:22s} {v:14s} index built in {time.time() - t0:.1f}s", flush=True)
            for j in pj:
                t = time.perf_counter()
                hits = r.search_job(j, k=10, filters=EVIDENCE_TYPES)
                ms = (time.perf_counter() - t) * 1000
                ids = [h["evidence_id"] for h, _ in hits]
                row = {"variant": v, "persona": persona, "style": j["style"], "job_id": j["job_id"], "latency_ms": round(ms, 1),
                       "returned": len(ids), "top5": ids[:5], "tag": tag}
                if j["gold_evidence"]:
                    row.update(metrics(ids, j["gold_evidence"]))
                rows.append(row)
    return rows


def summarise(rows: list[dict]) -> dict:
    groups = defaultdict(list)
    for r in rows:
        for key in [("all",), ("persona", r["persona"]), ("style", r["style"])]:
            groups[(r["variant"],) + key].append(r)
    out = {}
    for key, rs in groups.items():
        scored = [r for r in rs if "recall@5" in r]
        off = [r for r in rs if r["style"] == "off_niche"]
        out["|".join(key)] = {
            "n": len(scored),
            "recall@5": round(statistics.mean(r["recall@5"] for r in scored), 3) if scored else None,
            "mrr": round(statistics.mean(r["mrr"] for r in scored), 3) if scored else None,
            "ndcg@10": round(statistics.mean(r["ndcg@10"] for r in scored), 3) if scored else None,
            "refused_in_niche": round(sum(r["returned"] == 0 for r in scored) / len(scored), 3) if scored else None,
            "false_evidence_off_niche": round(sum(r["returned"] > 0 for r in off) / len(off), 3) if off else None,
            "p50_ms": round(statistics.median(r["latency_ms"] for r in rs), 1),
            "p95_ms": round(p95([r["latency_ms"] for r in rs]), 1),
        }
    return out


def table(summary: dict, variants: list[str], header: str) -> str:
    lines = [header, "", "| Variant | Recall@5 | MRR | nDCG@10 | Refused (in-niche) | False evidence (off-niche) | p50 ms | p95 ms |",
             "|---|---|---|---|---|---|---|---|"]
    for v in variants:
        s = summary[f"{v}|all"]
        lines.append(f"| {v} | {s['recall@5']} | {s['mrr']} | {s['ndcg@10']} | {s['refused_in_niche']} | "
                     f"{s['false_evidence_off_niche']} | {s['p50_ms']} | {s['p95_ms']} |")
    for dim in ("persona", "style"):
        vals = sorted({k.split("|")[2] for k in summary if k.split("|")[1] == dim and summary[k]["n"]})
        lines += ["", f"**Recall@5 by {dim}**", "", "| Variant | " + " | ".join(vals) + " |", "|---" * (len(vals) + 1) + "|"]
        for v in variants:
            lines.append(f"| {v} | " + " | ".join(str(summary[f"{v}|{dim}|{x}"]["recall@5"]) for x in vals) + " |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", nargs="+", default=["bm25"] + VARIANTS)
    ap.add_argument("--embedder", default=None, help="override embedding model ('hash' = test only)")
    ap.add_argument("--reranker", default=None, help="override reranker ('overlap' = test only)")
    ap.add_argument("--name", default="rag")
    a = ap.parse_args()
    rc = cfg()["rag"]
    overrides = {k: v for k, v in {"embedder": a.embedder, "reranker": a.reranker}.items() if v}
    emb, rr = a.embedder or rc["embedding_model"], a.reranker or rc["reranker_model"]
    test_only = emb == "hash" or rr == "overlap"
    tag = f"embedder={emb}; reranker={rr}" + ("; TEST-ONLY MODELS, DO NOT REPORT" if test_only else "")
    print(f"Running {a.variants} ({tag})")
    rows = run(a.variants, overrides, tag)
    summary = summarise(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{a.name}_results.json").write_text(json.dumps({"tag": tag, "summary": summary, "rows": rows}, indent=1), encoding="utf-8")
    with (OUT / f"{a.name}_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["variant", "group", "value", "n", "recall@5", "mrr", "ndcg@10", "refused_in_niche", "false_evidence_off_niche", "p50_ms", "p95_ms"])
        for k, s in summary.items():
            parts = k.split("|")
            w.writerow([parts[0], parts[1], parts[2] if len(parts) > 2 else "", *s.values()])
    md = table(summary, a.variants, f"### Retrieval results ({tag})")
    (OUT / f"{a.name}_table.md").write_text(md, encoding="utf-8")
    print("\n" + md)


if __name__ == "__main__":
    main()
