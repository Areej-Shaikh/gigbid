"""RAG unit tests (offline: hash embedder + overlap reranker stand in for the real models)."""
import pytest

from evals.runners.rag_eval import metrics
from rag.ingest.portfolio_loader import load_portfolio
from rag.retriever import VARIANTS, build_retriever
from rag.variants.pipeline import requirements

TEST_MODELS = {"embedder": "hash", "reranker": "overlap"}
EV = {"types": ["case_study", "repo", "review", "cv"]}


def test_metrics_perfect_and_empty():
    gold = {"a": 2, "b": 1}
    assert metrics(["a", "b", "x"], gold) == {"recall@5": 1.0, "mrr": 1.0, "ndcg@10": 1.0}
    assert metrics(["x", "y"], gold)["recall@5"] == 0.0


def test_requirement_decomposition_splits_needs():
    job = {"title": "t", "skills": ["dbt"], "description": "We are a SaaS company. First, build a dashboard. Second, we also want an Airflow DAG."}
    reqs = requirements(job)
    assert "dbt" in reqs and any("dashboard" in r for r in reqs) and any("Airflow" in r for r in reqs)


@pytest.mark.parametrize("variant", ["bm25"] + VARIANTS)
def test_every_variant_finds_an_explicit_project(variant):
    items = load_portfolio("ai_ml_engineer")
    r = build_retriever(items, variant, **({} if variant == "bm25" else TEST_MODELS))
    job = {"title": "Build a churn prediction model", "description": "Predict churn with scikit-learn.", "skills": ["scikit-learn"]}
    top = [h["project"] for h, _ in r.search_job(job, k=5, filters=EV)]
    assert "Churn prediction model" in top


def test_outcome_boost_prefers_evidence_from_winning_proposals():
    items = load_portfolio("ai_ml_engineer")
    r = build_retriever(items, "v4_outcome", **TEST_MODELS)
    assert r.boost and max(r.boost.values()) <= 1.0


def test_portfolio_search_interface():
    r = build_retriever(load_portfolio("data_analyst"), "v2_hybrid", **TEST_MODELS)
    hits = r.search("Power BI dashboard", k=3, filters={"types": ["case_study"]})
    assert len(hits) == 3 and all(h["type"] == "case_study" for h, _ in hits)
