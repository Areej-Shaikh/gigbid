### Retrieval results (embedder=BAAI/bge-small-en-v1.5; reranker=Xenova/ms-marco-MiniLM-L-6-v2)

| Variant | Recall@5 | MRR | nDCG@10 | Refused (in-niche) | False evidence (off-niche) | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|
| bm25 | 0.64 | 0.835 | 0.702 | 0.0 | 1.0 | 4.3 | 10.7 |
| v0_naive | 0.678 | 0.8 | 0.715 | 0.0 | 1.0 | 29.4 | 52.3 |
| v1_decompose | 0.561 | 0.684 | 0.52 | 0.0 | 1.0 | 50.3 | 100.5 |
| v2_hybrid | 0.713 | 0.838 | 0.751 | 0.0 | 1.0 | 29.4 | 37.8 |
| v3_rerank | 0.659 | 0.812 | 0.714 | 0.0 | 1.0 | 1747.7 | 3060.1 |
| v4_outcome | 0.447 | 0.623 | 0.561 | 0.0 | 1.0 | 1859.7 | 2980.4 |
| v8_corrective | 0.278 | 0.385 | 0.302 | 0.597 | 0.0 | 3756.3 | 9988.8 |

**Recall@5 by persona**

| Variant | ai_ml_engineer | data_analyst | fullstack_developer |
|---|---|---|---|
| bm25 | 0.618 | 0.68 | 0.621 |
| v0_naive | 0.646 | 0.705 | 0.683 |
| v1_decompose | 0.467 | 0.588 | 0.629 |
| v2_hybrid | 0.673 | 0.791 | 0.675 |
| v3_rerank | 0.605 | 0.744 | 0.629 |
| v4_outcome | 0.458 | 0.433 | 0.45 |
| v8_corrective | 0.254 | 0.326 | 0.254 |

**Recall@5 by style**

| Variant | explicit | multi | synonym | vague |
|---|---|---|---|---|
| bm25 | 0.918 | 0.711 | 0.624 | 0.306 |
| v0_naive | 0.908 | 0.672 | 0.682 | 0.45 |
| v1_decompose | 0.622 | 0.578 | 0.672 | 0.372 |
| v2_hybrid | 0.901 | 0.783 | 0.721 | 0.446 |
| v3_rerank | 0.978 | 0.567 | 0.71 | 0.383 |
| v4_outcome | 0.96 | 0.322 | 0.3 | 0.207 |
| v8_corrective | 0.931 | 0.094 | 0.061 | 0.026 |
