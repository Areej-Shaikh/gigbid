### Ablation (embedder=BAAI/bge-small-en-v1.5; reranker=Xenova/ms-marco-MiniLM-L-6-v2)

| Config | Recall@5 | Δ vs full | MRR | nDCG@10 |
|---|---|---|---|---|
| full | 0.46 | +0.000 | 0.627 | 0.567 |
| minus_decompose | 0.447 | -0.013 | 0.623 | 0.561 |
| minus_hybrid | 0.478 | +0.018 | 0.643 | 0.586 |
| minus_rerank | 0.29 | -0.170 | 0.433 | 0.392 |
| minus_outcome | 0.677 | +0.217 | 0.816 | 0.721 |
| v0_baseline | 0.678 | +0.218 | 0.8 | 0.715 |
