"""V2 hybrid (retrieval group): BM25 + dense fused with reciprocal rank fusion. Catches exact tool names."""
from rag.variants.pipeline import Pipeline

NAME = "v2_hybrid"
FLAGS = dict(hybrid=True)


def build(items, **overrides):
    return Pipeline(items, NAME, **{**FLAGS, **overrides})
