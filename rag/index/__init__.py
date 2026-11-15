"""Retrieval indexes (B1/B2).

Indexes are built in memory, per persona, when the Portfolio server first needs them, and rebuilt when any portfolio
file changes (mcp_servers/portfolio/core.py -> store(), rag/ingest/portfolio_loader.py -> portfolio_version()):
  - BM25 keyword index (rank_bm25): rag/retriever.py, the deployed retriever
  - dense vectors (BAAI/bge-small-en-v1.5 via fastembed, CPU) and the cross-encoder reranker: rag/variants/pipeline.py
A corpus of ~150 items per persona fits in memory in milliseconds, so no external vector database is needed; a
persistent store would only pay off for much larger portfolios.
"""
