"""Decision metrics on the dev set (B4): bid-or-skip F1, scam precision and recall, price inside the fair band,
unsupported claims, latency, tokens and cost. Runs the full bid graph up to the approval interrupt; nothing is submitted.

  python -m evals.runners.decision_eval                    # all 180 dev jobs
  python -m evals.runners.decision_eval --per-persona 10   # 30-job smoke version (what CI runs)

Same graph run as graph_eval (one implementation), without the simulated client step; see gigsim_outcomes.py for
reply and interview rates. Writes evals/results/<name>_results.json and <name>_table.md (default name: decisions).
"""
import sys

from evals.runners import graph_eval


def main():
    args = sys.argv[1:]
    if "--name" not in args:
        args += ["--name", "decisions"]
    sys.argv = [sys.argv[0], *args, "--no-outcomes"]
    graph_eval.main()


if __name__ == "__main__":
    main()
