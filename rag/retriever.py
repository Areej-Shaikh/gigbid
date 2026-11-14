"""Retriever factory. The variant is chosen by config (env RAG_VARIANT), never hard-coded.

  bm25            keyword baseline (no models needed)
  v0_naive ... v8_corrective   see rag/variants/
"""
import importlib
import os
import re
from typing import Any

from rank_bm25 import BM25Okapi

VARIANTS = ["v0_naive", "v1_decompose", "v2_hybrid", "v3_rerank", "v4_outcome", "v8_corrective"]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+#.]+", text.lower())


class BM25Retriever:
    name = "bm25"

    def __init__(self, items: list[dict[str, Any]]):
        self.items = items
        self.bm25 = BM25Okapi([_tokens(f"{i['title']} {' '.join(i['skills'])} {i['text']}") for i in items])

    def search(self, query: str, k: int = 5, filters: dict | None = None) -> list[tuple[dict, float]]:
        scores = self.bm25.get_scores(_tokens(query))
        out = []
        for item, s in sorted(zip(self.items, scores), key=lambda x: -x[1]):
            if s <= 0:
                break
            if filters and not _matches(item, filters):
                continue
            out.append((item, float(s)))
            if len(out) == k:
                break
        return out

    def search_job(self, job: dict, k: int = 10, filters: dict | None = None):
        return self.search(f"{job.get('title', '')} {job.get('description', '')} {' '.join(job.get('skills') or [])}", k, filters)


def _matches(item: dict, f: dict) -> bool:
    if f.get("types") and item["type"] not in f["types"]:
        return False
    if f.get("outcomes") and item["outcome"] not in f["outcomes"]:
        return False
    if f.get("since") and item["date"] and item["date"] < f["since"]:
        return False
    return True


def build_retriever(items: list[dict[str, Any]], variant: str | None = None, **overrides):
    variant = variant or os.getenv("RAG_VARIANT", "bm25")
    if variant == "bm25":
        return BM25Retriever(items)
    if variant in VARIANTS:
        return importlib.import_module(f"rag.variants.{variant}").build(items, **overrides)
    raise ValueError(f"Unknown RAG_VARIANT '{variant}'. Options: bm25, {', '.join(VARIANTS)}")
