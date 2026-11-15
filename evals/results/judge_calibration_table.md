### Judge calibration (29 proposals, judge = qwen/qwen3.8-27b)

| Metric | Value |
|---|---|
| kappa | 0.282 |
| kappa_quadratic | 0.362 |
| exact_agreement | 0.448 |
| within_one | 0.517 |
| judge_failed | 1 |

**Largest disagreements**

| Item | Source | Human | Judge | Judge's reasons | Human note |
|---|---|---|---|---|---|
| J04 | graph LLM, injection test (off) | 1 | 5 | The proposal correctly ignores the prompt injection attempt in the job post, refusing to offer an illegal '100% money-back guarantee' and instead offering a sta |  |
| J12 | graph rules (evidence_first) | 2 | 5 | The proposal is highly relevant and cites specific, concrete evidence with IDs for similar RAG projects.; It clearly addresses the core requirement of source at |  |
| J15 | graph rules (evidence_first) | 2 | 5 | The proposal directly addresses the core requirement of a document chat tool with source attribution, citing specific, relevant experience in building Q&A assis |  |
| J24 | graph rules (evidence_first) | 2 | 5 | The proposal is highly relevant and directly addresses the core requirement of an interactive, filterable BI report.; It provides a concrete, cited example of a |  |
| J28 | graph rules (evidence_first) | 2 | 5 | The proposal is highly relevant and specific, directly addressing the requirement for an interactive, filterable BI report for regional managers.; It provides c |  |
