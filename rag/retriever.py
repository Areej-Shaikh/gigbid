"""Retriever factory. The variant is chosen by config (RAG_VARIANT), never hard-coded.

Right now only a BM25 keyword baseline exists. Part B adds V0 (naive dense, required baseline)
and the advanced variants in rag/variants/, then the evaluation decides which one ships.
"""
import os
import re
from typing import Any

from rank_bm25 import BM25Okapi


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+#.]+", text.lower())


class BM25Retriever:
    name = "bm25"

    def __init__(self, items: list[dict[str, Any]]):
        self.items = items
        docs = [_tokens(f"{i['title']} {' '.join(i['skills'])} {i['text']}") for i in items]
        self.bm25 = BM25Okapi(docs)

    def search(self, query: str, k: int = 5, filters: dict | None = None) -> list[tuple[dict, float]]:
        scores = self.bm25.get_scores(_tokens(query))
        ranked = sorted(zip(self.items, scores), key=lambda x: -x[1])
        out = []
        for item, s in ranked:
            if s <= 0:
                break
            if filters and not _matches(item, filters):
                continue
            out.append((item, float(s)))
            if len(out) == k:
                break
        return out


def _matches(item: dict, f: dict) -> bool:
    if f.get("types") and item["type"] not in f["types"]:
        return False
    if f.get("outcomes") and item["outcome"] not in f["outcomes"]:
        return False
    if f.get("since") and item["date"] and item["date"] < f["since"]:
        return False
    return True


def build_retriever(items: list[dict[str, Any]], variant: str | None = None):
    variant = variant or os.getenv("RAG_VARIANT", "bm25")
    if variant == "bm25":
        return BM25Retriever(items)
    raise ValueError(f"Unknown RAG_VARIANT '{variant}' (implemented: bm25)")
