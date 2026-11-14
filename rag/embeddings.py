"""Open embedding + reranker models (CPU, via fastembed / ONNX). Downloaded once, then cached.

"hash" is a tiny fake embedder used ONLY by unit tests / offline smoke runs. Never report its numbers.
"""
import functools
import hashlib
import math
import re

import numpy as np


class HashEmbedder:
    name = "hash-test-only"

    def __init__(self, dim: int = 512):
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            toks = re.findall(r"[a-z0-9]+", t.lower())
            for tok in toks + [a + " " + b for a, b in zip(toks, toks[1:])]:
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                out[i, h % self.dim] += 1 if (h >> 20) % 2 else -1
        return out


class FastEmbedder:
    def __init__(self, model: str):
        from fastembed import TextEmbedding
        self.name = model
        self.model = TextEmbedding(model)

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.array(list(self.model.embed(texts, batch_size=32)), dtype=np.float32)


class FastReranker:
    def __init__(self, model: str):
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        self.name = model
        self.model = TextCrossEncoder(model)

    def score(self, query: str, docs: list[str]) -> list[float]:
        return [1 / (1 + math.exp(-s)) for s in self.model.rerank(query, docs)]   # logits -> probability


class OverlapReranker:
    """Test-only stand-in for a cross-encoder (word overlap)."""
    name = "overlap-test-only"

    def score(self, query: str, docs: list[str]) -> list[float]:
        q = set(re.findall(r"[a-z0-9]{4,}", query.lower()))
        return [len(q & set(re.findall(r"[a-z0-9]{4,}", d.lower()))) / max(len(q), 1) for d in docs]


@functools.lru_cache
def get_embedder(model: str):
    return HashEmbedder() if model == "hash" else FastEmbedder(model)


@functools.lru_cache
def get_reranker(model: str):
    return OverlapReranker() if model == "overlap" else FastReranker(model)
