# GigBid: R&D Report

**AI-4016 R&D Assignment: a multi-agent freelancer copilot**
Live demo: https://gigbid-wtvi.onrender.com · Code: https://github.com/Areej-Shaikh/gigbid

## 1. Problem and approach

Freelancers spend paid "Connects" on every proposal, and most proposals get no reply. Generic, AI-written
proposals make this worse. GigBid's goal is **fewer, better bids**: skip jobs that are scams or out of niche,
and write short proposals in which every claim is backed by real evidence from the freelancer's own portfolio.
A human approves every proposal and message before anything is sent.

Design principles:
1. **Explicit graph, typed handoffs.** LLMs do bounded work inside nodes; they never decide control flow or touch write tools (ADR 0001).
2. **Least-privilege tools over MCP.** Agents that read untrusted text have no write tools; writes happen only after a human approval interrupt (ADR 0002).
3. **Everything measurable.** Every claim in this report comes from a reproducible run in `evals/results/`.
4. **Degrade, never die.** Each LLM node has a rule-based fallback (ADR 0004); runs and approvals are durable (ADR 0005).

## 2. System

- **Bid graph:** Intake → Job Analyst ∥ Risk Assessor ∥ Fit Matcher → decide → Pricing → Writer → Claim Verifier → Critic (≤ 2 revisions) → Compliance Guard → dry-run preview → human approval → submit.
- **Conversation graph:** read messages → classify intent → (calendar slots) → Client Liaison draft → Compliance → preview → human approval → send (+ calendar hold).
- **MCP servers:** marketplace (GigSim adapter; rate limit; audit log), portfolio (RAG over the freelancer's case studies, repos and reviews), workspace (calendar, email drafts).
- **Memory:** style rules promoted from repeated human edits; outcome statistics per job category.
- **Platform:** FastAPI + React with live SSE timelines; Postgres checkpoints; OpenTelemetry traces end to end; CI with an evaluation gate; deployed on Render.

Full details: `docs/ARCHITECTURE.md`.

## 3. Data

GigSim is a mock marketplace built from public Kaggle job and price data plus synthetic clients (`docs/DATA_CARD.md`).
The **dev set** has 180 labelled jobs: 3 freelancer personas × 6 job styles (explicit, vague, synonym, multi-requirement,
off-niche, scam), with gold evidence per job and a fair price band. Simulated clients reply more often to proposals
that cite evidence, mention the client's skills and avoid generic openings. **Outcome numbers are simulated, not real.**

## 4. Results

### 4.1 Retrieval (Recall@5 / MRR / nDCG@10 over gold evidence)

| Variant | Recall@5 | MRR | nDCG@10 | p95 latency |
|---|---|---|---|---|
| BM25 | 0.640 | 0.835 | 0.702 | 11 ms |
| V0 dense | 0.678 | 0.800 | 0.715 | 52 ms |
| V1 query decomposition | 0.561 | 0.684 | 0.520 | 101 ms |
| **V2 hybrid (BM25 + dense, RRF)** | **0.713** | **0.838** | **0.751** | 38 ms |
| V3 + cross-encoder rerank | 0.659 | 0.812 | 0.714 | 3.1 s |
| V4 + outcome boost | 0.447 | 0.623 | 0.561 | 3.0 s |
| V8 corrective (refuse weak evidence) | 0.278 | 0.385 | 0.302 | 10 s |

By job style, every retriever is strong on explicit posts (BM25 0.92) and weak on vague ones (BM25 0.31, V2 0.45).
V8 is the only variant that refuses to return evidence for off-niche jobs (false-evidence rate 0.0 vs 1.0), but it
also refuses 60% of in-niche requirements, so it is too conservative to ship.

**Ablation** (removing one component from the full V4 pipeline): removing the reranker costs the most (−0.17 Recall@5);
removing the outcome boost *improves* recall by 0.22. The outcome prior, learned from too few outcomes, pushed generic
"winning" evidence above relevant evidence.

### 4.2 Retrieval quality is not decision quality

Full bid graph, 180 jobs, rule-based profile:

| | BM25 | V2 @ 0.025 | V2 @ 0.02 | V2 @ 0.017 |
|---|---|---|---|---|
| Bid precision | 0.923 | 0.937 | 0.887 | 0.864 |
| Bid recall | 0.910 | 0.826 | 0.868 | 0.924 |
| **Bid F1** | **0.916** | 0.878 | 0.877 | 0.893 |
| Critic approved | 89.7% | 75.9% | 73.9% | 70.3% |

With simulated outcomes (BM25 vs V2 @ 0.017): wasted bids on skip-labelled jobs **11 vs 21**, reply rate 61.3% vs
55.8%, interview rate 27.5% vs 20.8%. The reply-rate difference is not statistically significant (p = 0.34).

**Finding:** the retriever with the best recall made worse bid decisions. Hybrid fusion gives every job some
"related" evidence, so the Fit Matcher sees coverage on off-niche jobs and over-bids; sweeping the coverage
threshold trades precision for recall but never beats BM25's F1. **Decision:** ship BM25 (ADR 0003). It is also the
only option that fits the free deployment (no model download, 11 ms p95).

### 4.3 Claim verification

On a 30-job LLM run (Groq; all bid-labelled jobs), the writer produced **0.67 unsupported claims per proposal**
(claims whose cited evidence did not contain them, or with no citation). The Claim Verifier removed all of them
before the Critic: **0 unsupported claims reached the human**. CI enforces `unsupported_after = 0`.

### 4.4 Safety

- **Scams:** scam precision and recall 1.0 on the 12 scam jobs in the dev set (rule-based Risk Assessor).
- **Prompt injection:** see 4.5.
- **Durability:** killing the API container while a proposal waited for approval, restarting, and approving
  produced exactly one proposal and charged Connects once (Postgres checkpoints + idempotency keys).
- **Privacy:** an integration test sends a client message with an email, phone number and card number through
  the whole system and checks that none of them appear in exported trace spans.

### 4.5 Prompt-injection attack success rate

42 attacks (24 hidden in real job posts, 18 in client messages; 8–9 attacker goals; direct, fake-"system" and covert
phrasing) were run through the real graphs with the defence layers switched off and on.
Method and per-layer attribution: `docs/SECURITY.md`.

_Results table: filled from `evals/results/injection_table.md` when the run completes._

### 4.6 Cost and latency

Rule-based profile: p50 0.24 s, p95 0.45 s per job. LLM profile (Groq open models): p50 34 s, p95 69 s per job,
about 8,100 tokens per analysed job. At the listed Groq prices that is well under $0.01 per job (cost per node is
recorded in each trace; prices in `config.yaml` should be re-checked before quoting).

## 5. Failure analysis

| # | Failure | Cause | Fix / status |
|---|---|---|---|
| 1 | Best-recall retriever made worse bids (4.2) | Fusion scores are not comparable to a fixed coverage threshold; loosely related evidence counts as coverage | Shipped BM25; per-retriever thresholds in config; open: calibrate the threshold per persona |
| 2 | Outcome boost (V4) hurt recall by 0.22 | Prior learned from too few outcomes favours generic evidence | Disabled in the deployed variant; needs a minimum-sample rule like the outcome memory has |
| 3 | Vague job posts: Recall@5 0.31 (BM25) | No keyword overlap with the evidence | Open: query rewriting by the Job Analyst before retrieval |
| 4 | Writer re-used the same unsupported claim in every revision, so the critic loop never converged | The writer was not told *which* claims were removed | The verifier's removed claims and reasons are now fed back to the writer |
| 5 | Writer reversed numbers ("fell from 13% to 22%") | Synthetic evidence had the direction wrong in generation, and prompts did not ask to keep direction | Fixed the generator; writer prompt requires copying numbers with their direction |
| 6 | Every LLM cost showed $0 | `config.yaml` had two `pricing:` keys; YAML silently kept the second | Renamed to `llm_pricing`; a test now fails on any duplicate config key |
| 7 | Injection evaluation looked perfect, but the agents had silently fallen back to templates | Free-tier daily quota exhausted; fallbacks hide provider errors | Runner marks such cases invalid and stops at the daily limit; per-minute limits are now waited out |
| 8 | Configured fallback model returned 404 | Groq retired `llama-3.1-8b-instant` | Fallback changed to `gpt-oss-120b`; failure surfaced by the validity check in #7 |
| 9 | Two users analysing the same job would share one run | Threads keyed by job id only | Threads, runs, events and index keyed by user (tenant scoping), with a test |
| 10 | Conversation run crashed silently | A duplicate keyword argument in a background task; the exception was never observed | Background tasks now log crashes and tell the UI |
| 11 | Masking turned dates into "[PHONE]" | Phone regex too broad | Phone needs 9+ digits and must not be an ISO date |

## 6. Limitations and scope cuts

Stated honestly, in order of impact:
- **Mock marketplace only.** The live Upwork adapter (OAuth, encrypted tokens) and a GitHub MCP server were not built.
- **LLM evaluations are small.** Groq's free tier allows about 200k tokens per model per day; one full LLM pass over
  the dev set needs about 1.5M. Large-scale numbers therefore use the rule-based profile, and LLM numbers come from
  30-job and 42-attack runs.
- **Outcomes are simulated.** Reply rates measure what GigSim's simulated clients reward, not real clients.
- **Not done:** calibrated LLM judge (Cohen's κ against hand labels), human pairwise panel, R&D question A
  (tool granularity), PDF CV / GitHub ingestion, background worker with schedules, signature extension.

## 7. What I would do next

1. Calibrate an LLM judge on 30 hand-labelled proposals, then use it to compare BM25 and V2 *proposal quality*, not only decisions.
2. Query rewriting for vague posts (largest retrieval gap).
3. Run the LLM evaluations on a paid tier for statistically meaningful sample sizes.
4. Live marketplace adapter behind the existing port, reusing the same allowlists and approval flow.
