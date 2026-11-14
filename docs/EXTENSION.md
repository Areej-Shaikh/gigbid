# Signature extension: X2 Proposal experiments

**What:** two proposal-writing strategies run as an A/B test in GigSim, with significance tests on the simulated
client reply rate. The experiment is a product feature, not just an evaluation script: production can split
jobs between strategies and record which strategy wrote each proposal.

## The two strategies

| Arm | Structure | Prompt |
|---|---|---|
| `evidence_first` (control) | client's problem → 2–3 cited results → short plan → rate | `agent/prompts/writer_strategy_evidence_first.md` |
| `plan_first` | client's problem → concrete delivery plan and milestones → one cited result → rate | `agent/prompts/writer_strategy_plan_first.md` |

Both strategies obey every rule of the writer prompt (citations, no contact details, length limits), so the
experiment changes the *structure* of the pitch only. The rule-based fallback writer has a matching variant for each
arm, so the experiment also runs without an LLM.

## How it works

- `agent/config.yaml → experiment`: arms, split, `enabled`, `force_arm`.
- `agent/experiments.py::assign_arm(job_id)`: a stable hash of experiment name + job id picks the arm, so a job keeps its
  arm across retries, resumes and replays (no strategy switching mid-thread).
- The writer appends the arm's prompt to its system prompt and records `strategy=<arm>` in the run trace, so
  outcomes can be attributed to an arm.
- `GIGBID_ARM` forces one arm (used by the evaluation to run every job under both arms).

## Measurement

`LLM_PROFILE=fake RAG_VARIANT=bm25 python -m evals.runners.ab_test` runs all 180 dev jobs through the full bid
graph under **both** arms, approves (simulation only), submits to GigSim and records the simulated client's reaction.
Two analyses, both in `evals/results/ab_test_table.md`:

1. **Realistic A/B:** each job counts only in the arm its hash assigns (what production would see); Fisher exact test
   and a two-proportion z-test.
2. **Paired:** the same job under both arms; exact McNemar test on the discordant pairs (more power).

The tests are implemented in `evals/stats.py` (no SciPy) and checked against textbook values.

## Result

| | evidence_first | plan_first |
|---|---|---|
| Paired reply rate (142 jobs submitted under both arms) | **61.3%** | 54.2% |
| Realistic hash split | 68.8% (n = 77) | 55.4% (n = 65) |
| Interview rate (paired) | 39/142 | 30/142 |
| Average letter length | 114 words | 105 words |

- Paired: 34 jobs got a reply only with `evidence_first`, 24 only with `plan_first`; **exact McNemar p = 0.24**.
- Realistic split: **Fisher p = 0.12**. With about 70 jobs per arm, only a difference of about 24 points could be detected with
  80% power, so this experiment is underpowered for realistic effects.

**Decision:** the difference is not significant, so by the pre-set rule the control ships (`enabled: false`, all jobs
use `evidence_first`). Turning `enabled: true` back on keeps collecting evidence in production.

## Limitations

- The simulated clients reward citations, the client's own skills and the absence of generic openings. Both arms
  satisfy all three, so most of the measured gap is sampling noise in the simulator, which is exactly what the test
  says. A real-world test needs real clients and far more proposals.
- The run above uses the rule-based writer (no LLM quota limits, 360 graph runs). The same runner works with the LLM
  profile (`--per-persona N` for a smaller sample).
