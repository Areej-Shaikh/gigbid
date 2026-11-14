"""One configurable retrieval pipeline; each variant file (v0_naive.py, v2_hybrid.py, ...) is a config of it.

Steps (each can be switched on/off, which also makes ablation easy):
  chunk -> [decompose job into requirements] -> dense (+ BM25, fused with RRF) -> item level (best chunk)
        -> [cross-encoder rerank] -> [outcome-aware boost] -> [corrective: re-query, else refuse]
"""
import os
import re
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi

from agent.config import cfg
from rag.embeddings import get_embedder, get_reranker

RRF_K = 60


def _tok(t: str) -> list[str]:
    return re.findall(r"[a-z0-9+#.]+", t.lower())


def requirements(job: dict) -> list[str]:
    """Split a job into separate requirements (simple + explainable; the LLM JobSpec can replace this)."""
    sents = [s.strip() for s in re.split(r"[.;\n!?]+|\bfirst,|\bsecond,|\balso\b", job.get("description", ""), flags=re.I)
             if len(s.strip()) > 12 and not re.match(r"^(hi|we are a|small|our .* startup|timeline|please)", s.strip(), re.I)]
    reqs = list(job.get("skills") or []) + sents
    return reqs[:8] or [job.get("title", "")]


def job_text(job: dict) -> str:
    return f"{job.get('title', '')}. {job.get('description', '')} {' '.join(job.get('skills') or [])}".strip()


class Pipeline:
    def __init__(self, items: list[dict[str, Any]], name: str, *, decompose=False, hybrid=False, rerank=False,
                 outcome=False, corrective=False, embedder: str | None = None, reranker: str | None = None):
        rc = cfg()["rag"]
        self.name, self.items = name, items
        self.decompose, self.hybrid, self.rerank, self.outcome, self.corrective = decompose, hybrid, rerank, outcome, corrective
        self.emb = get_embedder(embedder or os.getenv("RAG_EMBEDDER", rc["embedding_model"]))
        self.rr = get_reranker(reranker or os.getenv("RAG_RERANKER", rc["reranker_model"])) if (rerank or corrective) else None
        self.rc = rc
        # fixed-size chunks; every chunk remembers its item
        self.chunks, self.owner = [], []
        for i, it in enumerate(items):
            text = f"{it['title']}\n{it['text']}"
            for s in range(0, max(len(text), 1), rc["chunk_chars"]):
                self.chunks.append(text[s:s + rc["chunk_chars"]]); self.owner.append(i)
        self.owner = np.array(self.owner)
        vecs = self.emb.embed(self.chunks)
        self.vecs = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)
        self.bm25 = BM25Okapi([_tok(c) for c in self.chunks]) if hybrid else None
        self.boost = self._outcome_boost() if outcome else {}

    # ---------------------------------------------------------------- building blocks
    def _outcome_boost(self) -> dict[str, float]:
        """Evidence cited in proposals that WON (1.0) or got a REPLY (0.5) gets a boost (0..1)."""
        score, count = {}, {}
        for it in self.items:
            if it["type"] == "proposal":
                val = {"won": 1.0, "replied": 0.5}.get(it["outcome"], 0.0)
                for e in it.get("cited", []):
                    score[e] = score.get(e, 0) + val; count[e] = count.get(e, 0) + 1
        return {e: score[e] / count[e] for e in score}

    def _chunk_ranking(self, query: str) -> list[tuple[int, float]]:
        q = self.emb.embed([query])[0]
        q = q / (np.linalg.norm(q) + 1e-9)
        dense = self.vecs @ q
        order = np.argsort(-dense)
        if not self.hybrid:
            return [(int(c), float(dense[c])) for c in order]
        bm = self.bm25.get_scores(_tok(query))
        rrf = np.zeros(len(self.chunks))
        rrf[order] += 1 / (RRF_K + np.arange(1, len(order) + 1))
        b_order = np.argsort(-bm)
        rrf[b_order] += 1 / (RRF_K + np.arange(1, len(b_order) + 1))
        return [(int(c), float(rrf[c])) for c in np.argsort(-rrf)]

    def _item_ranking(self, query: str, allowed: set[int]) -> list[tuple[int, float, str]]:
        """Best chunk per item -> (item_idx, score, best_chunk_text)."""
        seen, out = set(), []
        for c, s in self._chunk_ranking(query):
            i = int(self.owner[c])
            if i in seen or i not in allowed:
                continue
            seen.add(i); out.append((i, s, self.chunks[c]))
        return out

    def _allowed(self, filters: dict | None) -> set[int]:
        f = filters or {}
        ok = set()
        for i, it in enumerate(self.items):
            if f.get("types") and it["type"] not in f["types"]:
                continue
            if f.get("outcomes") and it["outcome"] not in f["outcomes"]:
                continue
            if f.get("since") and it["date"] and it["date"] < f["since"]:
                continue
            ok.add(i)
        return ok

    # ---------------------------------------------------------------- main entry points
    def search_job(self, job: dict, k: int = 10, filters: dict | None = None) -> list[tuple[dict, float]]:
        allowed = self._allowed(filters)
        queries = requirements(job) if self.decompose else [job_text(job)]
        # fuse per-requirement rankings with RRF (so every requirement gets a voice)
        fused: dict[int, float] = {}
        best_text: dict[int, str] = {}
        for q in queries:
            ranking = self._item_ranking(q, allowed)
            for rank, (i, s, txt) in enumerate(ranking[:50]):
                fused[i] = fused.get(i, 0) + (1 / (RRF_K + rank + 1) if len(queries) > 1 else s)
                best_text.setdefault(i, txt)
        ranked = sorted(fused.items(), key=lambda x: -x[1])
        if self.rerank or self.corrective:
            ranked = self._rerank(job_text(job), ranked[: self.rc["candidates"]], best_text)
        if self.outcome:
            w = self.rc["outcome_weight"]
            ranked = sorted(((i, s + w * self.boost.get(self.items[i]["evidence_id"], 0)) for i, s in ranked), key=lambda x: -x[1])
        if self.corrective:
            ranked = self._correct(job, ranked, allowed)
        return [(self.items[i], float(s)) for i, s in ranked[:k]]

    def _rerank(self, query: str, ranked, best_text) -> list[tuple[int, float]]:
        if not ranked:
            return []
        docs = [f"{self.items[i]['title']}. {best_text[i]}" for i, _ in ranked]
        scores = self.rr.score(query, docs)
        return sorted(((i, s) for (i, _), s in zip(ranked, scores)), key=lambda x: -x[1])

    def _correct(self, job: dict, ranked, allowed) -> list[tuple[int, float]]:
        """Corrective RAG: grade evidence; if weak, re-query with a rewritten query; if still weak, refuse (return [])."""
        thr = self.rc["corrective_min"]
        if ranked and ranked[0][1] >= thr:
            return [(i, s) for i, s in ranked if s >= thr]
        rewrite = " ".join((job.get("skills") or []) + [job.get("title", "")] + requirements(job)[:3])
        texts = {i: t for i, _, t in self._item_ranking(rewrite, allowed)[: self.rc["candidates"]]}
        retry = self._rerank(rewrite, [(i, 0.0) for i in texts], texts)
        good = [(i, s) for i, s in retry if s >= thr]
        return good   # empty list = "no evidence: do not claim this"

    def search(self, query: str, k: int = 5, filters: dict | None = None) -> list[tuple[dict, float]]:
        """Single-requirement search used by the Portfolio MCP server."""
        return self.search_job({"title": query, "description": "", "skills": []}, k, filters)
