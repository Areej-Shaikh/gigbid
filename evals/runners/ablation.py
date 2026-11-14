"""Ablation (R&D question B): take the full pipeline and remove ONE component at a time.

  python -m evals.runners.ablation          (add --embedder hash --reranker overlap for an offline smoke test)
Writes evals/results/ablation_results.json and ablation_table.md
"""
import argparse
import json
import statistics
from pathlib import Path

from agent.config import cfg
from evals.runners.rag_eval import DEV, EVIDENCE_TYPES, metrics
from rag.ingest.portfolio_loader import load_portfolio
from rag.variants.pipeline import Pipeline

FULL = dict(decompose=True, hybrid=True, rerank=True, outcome=True)
CONFIGS = {"full": FULL, **{f"minus_{k}": {**FULL, k: False} for k in FULL}, "v0_baseline": {}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--embedder"); ap.add_argument("--reranker")
    a = ap.parse_args()
    ov = {k: v for k, v in {"embedder": a.embedder, "reranker": a.reranker}.items() if v}
    rc = cfg()["rag"]
    tag = f"embedder={a.embedder or rc['embedding_model']}; reranker={a.reranker or rc['reranker_model']}"
    jobs = [j for j in json.loads(DEV.read_text(encoding="utf-8")) if j["gold_evidence"] and j["style"] != "scam"]
    res = {}
    for name, flags in CONFIGS.items():
        scores = []
        for persona in sorted({j["persona"] for j in jobs}):
            p = Pipeline(load_portfolio(persona), name, **flags, **ov)
            for j in (x for x in jobs if x["persona"] == persona):
                ids = [h["evidence_id"] for h, _ in p.search_job(j, 10, EVIDENCE_TYPES)]
                scores.append(metrics(ids, j["gold_evidence"]))
        res[name] = {m: round(statistics.mean(s[m] for s in scores), 3) for m in ("recall@5", "mrr", "ndcg@10")}
        print(name, res[name], flush=True)
    full = res["full"]["recall@5"]
    lines = [f"### Ablation ({tag})", "", "| Config | Recall@5 | Δ vs full | MRR | nDCG@10 |", "|---|---|---|---|---|"]
    for n, r in res.items():
        lines.append(f"| {n} | {r['recall@5']} | {r['recall@5'] - full:+.3f} | {r['mrr']} | {r['ndcg@10']} |")
    out = Path("evals/results")
    out.mkdir(parents=True, exist_ok=True)
    (out / "ablation_results.json").write_text(json.dumps({"tag": tag, "results": res}, indent=1), encoding="utf-8")
    (out / "ablation_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
