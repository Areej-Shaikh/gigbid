# ADR 0003: Deploy BM25, not the hybrid retriever with the best recall

**Status:** accepted

## Context
V2 hybrid retrieval (BM25 + dense, reciprocal rank fusion) had the best Recall@5 (0.713 vs 0.640 for BM25).
But retrieval scores feed the bid decision, and the end goal is good bids, not recall.

## Decision
Ship BM25 (`RAG_VARIANT=bm25`). Keep the variants selectable for evaluation.

## Evidence
Full bid graph on 180 dev jobs with simulated outcomes: BM25 bid F1 0.916 vs 0.893, wasted bids on
skip-jobs 11 vs 21, reply rate 61.3% vs 55.8% (difference not significant, p = 0.34). Hybrid finds loosely
related evidence for off-niche jobs and over-bids. BM25 also needs no model download and has p95 11 ms.

## Consequences
+ Cheaper, faster, deployable on the free tier, and at least as good end to end.
− Weaker on vague and synonym-heavy job posts (Recall@5 0.31 on vague posts); revisit with a calibrated threshold per retriever.
