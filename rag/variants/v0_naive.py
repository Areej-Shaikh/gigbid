"""V0 naive dense (required baseline): fixed chunks, top-k cosine on the whole job post."""
from rag.variants.pipeline import Pipeline

NAME = "v0_naive"
FLAGS = dict()


def build(items, **overrides):
    return Pipeline(items, NAME, **{**FLAGS, **overrides})
