"""Signature extension X2: two proposal strategies as an A/B test in GigSim, with significance tests.

  LLM_PROFILE=fake RAG_VARIANT=bm25 python -m evals.runners.ab_test          # all 180 dev jobs, both arms
  python -m evals.runners.ab_test --per-persona 5                              # small LLM run

Arms (agent/config.yaml -> experiment; instructions in agent/prompts/writer_strategy_<arm>.md):
  evidence_first   problem -> 2-3 cited results -> short plan -> rate
  plan_first       problem -> concrete delivery plan -> one cited result -> rate

Every job runs through the full bid graph under BOTH arms (GIGBID_ARM forces the arm), is approved
(simulation only), submitted to GigSim, and the simulated client's reaction is recorded. Two analyses:
  1. Realistic A/B: each job keeps only the arm its stable hash assigns (what production does), compared
     between groups with Fisher's exact test and a two-proportion z-test.
  2. Paired: the same job under both arms, compared with an exact McNemar test (more statistical power).
Writes evals/results/ab_test_results.json and ab_test_table.md
"""
import argparse
import asyncio
import json
import os
from pathlib import Path

from agent.config import cfg
from agent.experiments import assign_arm
from evals.runners.graph_eval import DEV, run, setup, stratified
from evals.stats import fisher_exact, mcnemar_exact, min_detectable_effect, two_proportion_z, wilson

OUT = Path("evals/results")
POSITIVE = {"replied", "interview", "hired"}


def rate(rows) -> str:
    k, n = sum(r["outcome"] in POSITIVE for r in rows), len(rows)
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.1%} [{lo:.0%}-{hi:.0%}]" if n else "-"


def analyse(by_arm: dict[str, dict[str, dict]], arms: list[str]) -> tuple[dict, str]:
    a, b = arms
    sub = lambda arm: [r for r in by_arm[arm].values() if r.get("outcome") in POSITIVE | {"ignored"}]  # noqa: E731
    # realistic split: each job only in the arm its hash assigns
    split = {arm: [r for r in sub(arm) if assign_arm_unforced(r["job_id"]) == arm] for arm in arms}
    ka, na = sum(r["outcome"] in POSITIVE for r in split[a]), len(split[a])
    kb, nb = sum(r["outcome"] in POSITIVE for r in split[b]), len(split[b])
    z, p_z = two_proportion_z(ka, na, kb, nb)
    p_f = fisher_exact(ka, na - ka, kb, nb - kb)
    # paired: jobs submitted under both arms
    both = [j for j in by_arm[a] if j in by_arm[b] and by_arm[a][j].get("outcome") in POSITIVE | {"ignored"}
            and by_arm[b][j].get("outcome") in POSITIVE | {"ignored"}]
    only_a = sum(by_arm[a][j]["outcome"] in POSITIVE and by_arm[b][j]["outcome"] not in POSITIVE for j in both)
    only_b = sum(by_arm[b][j]["outcome"] in POSITIVE and by_arm[a][j]["outcome"] not in POSITIVE for j in both)
    p_mc = mcnemar_exact(only_a, only_b)
    base = (ka + kb) / max(na + nb, 1)
    summary = {"arms": arms, "split_n": {a: na, b: nb}, "split_positive": {a: ka, b: kb}, "z": round(z, 3),
               "p_two_proportion_z": round(p_z, 4), "p_fisher": round(p_f, 4), "paired_jobs": len(both),
               "paired_only_a_positive": only_a, "paired_only_b_positive": only_b, "p_mcnemar": round(p_mc, 4),
               "min_detectable_effect_split": round(min_detectable_effect(base, min(na, nb) or 1), 3)}
    md = [f"| | {a} | {b} |", "|---|---|---|",
          f"| Realistic A/B (hash split) reply rate | {rate(split[a])} | {rate(split[b])} |",
          f"| Paired (same jobs, both arms) reply rate | {rate([by_arm[a][j] for j in both])} | {rate([by_arm[b][j] for j in both])} |",
          f"| Interview rate (paired) | {sum(by_arm[a][j]['outcome'] == 'interview' for j in both)}/{len(both)} | "
          f"{sum(by_arm[b][j]['outcome'] == 'interview' for j in both)}/{len(both)} |",
          f"| Avg letter words (paired) | {avg_words(by_arm[a], both)} | {avg_words(by_arm[b], both)} |", "",
          f"- Realistic split: Fisher exact p = {p_f:.3f}, two-proportion z = {z:.2f} (p = {p_z:.3f}). "
          f"With {min(na, nb)} jobs per arm, the smallest difference detectable with 80% power is "
          f"about {summary['min_detectable_effect_split']:.0%} (absolute).",
          f"- Paired: {only_a} jobs got a reply only with {a}, {only_b} only with {b}; exact McNemar p = {p_mc:.3f}."]
    return summary, "\n".join(md)


def avg_words(rows: dict, ids: list[str]) -> str:
    w = [rows[j].get("letter_words") for j in ids if rows[j].get("letter_words")]
    return f"{sum(w) / len(w):.0f}" if w else "-"


def assign_arm_unforced(job_id: str) -> str:
    forced = os.environ.pop("GIGBID_ARM", None)
    try:
        return assign_arm(job_id)
    finally:
        if forced is not None:
            os.environ["GIGBID_ARM"] = forced


async def run_arm(jobs, arm: str) -> list[dict]:
    os.environ["GIGBID_ARM"] = arm
    setup(jobs)                                          # fresh GigSim state per arm (Connects, proposals, messages)
    rows = await run(jobs, f"ab-{arm}")
    import gigsim.app as gigsim
    letters = {p["job_id"]: p["cover_letter"] for p in gigsim.state["proposals"].values()}
    for r in rows:
        r["arm"] = arm
        if r["job_id"] in letters:
            r["letter_words"] = len(letters[r["job_id"]].split())
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=0)
    ap.add_argument("--name", default="ab_test")
    a = ap.parse_args()
    jobs = json.loads(DEV.read_text(encoding="utf-8"))
    if a.per_persona:
        jobs = stratified(jobs, a.per_persona)
    arms = list(cfg()["experiment"]["arms"])[:2]
    all_rows = []
    for arm in arms:
        all_rows += asyncio.run(run_arm(jobs, arm))
    os.environ.pop("GIGBID_ARM", None)
    by_arm = {arm: {r["job_id"]: r for r in all_rows if r["arm"] == arm} for arm in arms}
    summary, md_body = analyse(by_arm, arms)
    tag = f"LLM profile={cfg()['profile']}; RAG_VARIANT={os.getenv('RAG_VARIANT', 'bm25')}; {len(jobs)} dev jobs per arm"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{a.name}_results.json").write_text(json.dumps({"tag": tag, "summary": summary, "rows": all_rows}, indent=1),
                                              encoding="utf-8")
    md = f"### X2 proposal A/B test in GigSim ({tag})\n\n" + md_body + "\n"
    (OUT / f"{a.name}_table.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
