"""GigSim outcomes on a fixed job set (B4): every draft the graph recommends is approved (simulation only),
submitted to GigSim, and the simulated client's reaction is recorded: reply rate, interview rate, and bids wasted on
jobs that should have been skipped. Decision metrics are reported alongside.

  python -m evals.runners.gigsim_outcomes                  # all 180 dev jobs (fixed set, deterministic clients)
  python -m evals.runners.gigsim_outcomes --per-persona 10

Same graph run as graph_eval (one implementation), with the simulated client step on. Writes
evals/results/<name>_results.json and <name>_table.md (default name: outcomes).
"""
import sys

from evals.runners import graph_eval


def main():
    args = [a for a in sys.argv[1:] if a != "--no-outcomes"]
    if "--name" not in args:
        args += ["--name", "outcomes"]
    sys.argv = [sys.argv[0], *args]
    graph_eval.main()


if __name__ == "__main__":
    main()
