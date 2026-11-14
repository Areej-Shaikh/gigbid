# AI usage



## Tools used

| Tool | Used for |
|---|---|
| Claude (claude.ai chat) | Planning: breaking the assignment into steps, step-by-step instructions for each milestone |
| Claude Code (VS Code extension) | Writing and editing code, tests, Docker/CI/Render config, running evaluations and tests, debugging, drafting documentation |
| GigBid's own LLMs (Groq open-weight models) | Inside the product: job analysis, proposal writing, claim verification, critique, client replies |

## How the work was split

**I decided and controlled:**
- The architecture and scope: which assignment items to build, in which order, and which to cut.
- Every commit and push. The assistant was told not to commit; when it once committed on its own, I had it undone.
- Running the system, checking results and screenshots, and the deployment on Render (account, secrets, logins).
- Accepting or rejecting design choices proposed by the assistant (e.g. shipping BM25 instead of hybrid retrieval after the threshold sweep).

**The AI assistants did:**
- Most of the code, following my step plans, plus tests for each component.
- Running evaluations and reporting the numbers, including negative results.
- First drafts of the documentation (README, architecture, ADRs, security, this report).

## Verification: how AI output was checked

- **Tests for everything that matters:** unit, integration (real graphs + MCP servers in process), MCP contract
  snapshots, Playwright end-to-end tests; CI runs them all plus a smoke evaluation with thresholds.
- **Numbers only from runs:** every metric in the README and report comes from a file in `evals/results/`.
- **Real end-to-end checks**, not just tests: crash/resume in Docker, one trace id across all processes in Phoenix,
  the live deployment.

## Where the AI got things wrong (and how it was caught)

| Mistake | How it was caught |
|---|---|
| The MCP client started subprocesses with whatever `python` was on PATH, not the project's interpreter | Tool calls failed in my terminal; fixed to use `sys.executable` |
| Installed a dependency into the wrong virtual environment | `ModuleNotFoundError` when I ran the tests |
| A duplicate `pricing:` key in config silently set every LLM cost to $0 | Noticed while verifying tracing cost numbers; a test now rejects duplicate keys |
| Reported an injection evaluation where the LLMs had silently fallen back to templates (results looked perfect) | Suspicious results investigated before reporting; the runner now marks such cases invalid |
| Claimed in a doc draft that runs were scoped per user when they were not | Checked the claim against the code; implemented tenant scoping with a test |
| Presented an F1 from a 30-job LLM sample that contained only bid-labelled jobs | Checked the sample composition; the README now reports only recall for that run |
| Committed code without being asked | I asked for the commit to be reverted; no further auto-commits |

## What I learned

- AI-generated code needs measurable checks: the most convincing failures (perfect-looking results) came from silent fallbacks.
- Better component metrics (retrieval recall) do not guarantee better system outcomes (bid decisions).
- Rate limits and quotas shape what can be evaluated; evaluation harnesses must detect degraded runs.
