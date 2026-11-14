"""V4 outcome-aware ranking (ranking group): V3 + boost evidence cited in past proposals that won or got replies."""
from rag.variants.pipeline import Pipeline

NAME = "v4_outcome"
FLAGS = dict(hybrid=True, rerank=True, outcome=True)


def build(items, **overrides):
    return Pipeline(items, NAME, **{**FLAGS, **overrides})
