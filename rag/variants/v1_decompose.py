"""V1 requirement decomposition (query group): one dense retrieval per extracted requirement, merged with RRF."""
from rag.variants.pipeline import Pipeline

NAME = "v1_decompose"
FLAGS = dict(decompose=True)


def build(items, **overrides):
    return Pipeline(items, NAME, **{**FLAGS, **overrides})
