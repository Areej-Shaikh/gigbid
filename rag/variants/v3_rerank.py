"""V3 cross-encoder reranking (retrieval group): V2 candidates re-scored by a cross-encoder for precision at small k."""
from rag.variants.pipeline import Pipeline

NAME = "v3_rerank"
FLAGS = dict(hybrid=True, rerank=True)


def build(items, **overrides):
    return Pipeline(items, NAME, **{**FLAGS, **overrides})
