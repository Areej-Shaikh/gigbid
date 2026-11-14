"""Fail (exit 1) if an evaluation result crosses the thresholds in evals/thresholds.json (E2, used by CI).

  python -m evals.runners.check_thresholds smoke          # checks evals/results/smoke_results.json
"""
import json
import sys
from pathlib import Path


def check(summary: dict, thresholds: dict) -> list[str]:
    fails = []
    for k, lo in thresholds.get("min", {}).items():
        v = summary.get(k)
        if v is None or v < lo:
            fails.append(f"{k} = {v} (must be >= {lo})")
    for k, hi in thresholds.get("max", {}).items():
        v = summary.get(k)
        if v is None or v > hi:
            fails.append(f"{k} = {v} (must be <= {hi})")
    return fails


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    summary = json.loads(Path(f"evals/results/{name}_results.json").read_text(encoding="utf-8"))["summary"]
    fails = check(summary, json.loads(Path("evals/thresholds.json").read_text(encoding="utf-8")))
    for k in ("bid_f1", "scam_recall", "reply_rate", "unsupported_claims_per_proposal_after", "p95_s"):
        print(f"  {k:40s} {summary.get(k)}")
    if fails:
        print("\nTHRESHOLDS FAILED:\n  " + "\n  ".join(fails))
        sys.exit(1)
    print("\nall thresholds met")


if __name__ == "__main__":
    main()
