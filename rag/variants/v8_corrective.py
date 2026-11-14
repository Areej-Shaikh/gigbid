"""V8 corrective RAG (agentic group): V3 + grade evidence, re-query when weak, refuse to claim when none."""
from rag.variants.pipeline import Pipeline

NAME = "v8_corrective"
FLAGS = dict(hybrid=True, rerank=True, corrective=True)


def build(items, **overrides):
    return Pipeline(items, NAME, **{**FLAGS, **overrides})
