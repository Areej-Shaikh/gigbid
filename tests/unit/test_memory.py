"""Long-term memory (R7): nothing is learned except through the promotion rules."""
import pytest
from langgraph.store.memory import InMemoryStore

from agent.config import cfg
from agent.memory.promotion_rules import (
    apply_style,
    edit_candidates,
    job_category,
    outcome_hint,
    record_edit,
    record_outcome,
    style_rules,
    style_violations,
)
from agent.memory.store import STYLE, STYLE_CANDIDATES, delete_memory, list_memory, ns

pytestmark = pytest.mark.anyio

BEFORE = ("I am very passionate about building chatbots. Your project needs a RAG chatbot over contracts. "
          "I built a contract Q&A assistant for a fintech client [ai_ml_engineer-case-01]. Let's talk here.")
CUT_FIRST = BEFORE.split(". ", 1)[1]
NO_WORD = BEFORE.replace("very passionate about", "focused on")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def fresh_cfg():
    cfg.cache_clear()
    yield
    cfg.cache_clear()


def test_edit_patterns_are_extracted_without_storing_text():
    keys = {c["key"] for c in edit_candidates(BEFORE, CUT_FIRST)}
    assert "cut_first_sentence" in keys
    word = edit_candidates(BEFORE, NO_WORD)
    assert {"avoid:passionate"} <= {c["key"] for c in word}
    assert all("before" not in c and "after" not in c for c in word)    # patterns only, never raw drafts


def test_a_big_rewrite_does_not_ban_every_deleted_word():
    rewrite = "Here is a completely different letter about dashboards and reporting for your team."
    assert not any(c["key"].startswith("avoid:") for c in edit_candidates(BEFORE, rewrite))


async def test_one_edit_is_not_enough_two_jobs_promote():
    store = InMemoryStore()
    assert await record_edit(store, "u1", "job-1", BEFORE, CUT_FIRST) == []
    assert await style_rules(store, "u1") == []                          # only a candidate so far
    assert await record_edit(store, "u1", "job-1", BEFORE, CUT_FIRST) == []   # same job again: still 1 job
    promoted = await record_edit(store, "u1", "job-2", BEFORE, CUT_FIRST)
    assert "cut_first_sentence" in promoted
    rule = (await store.aget(ns(STYLE, "u1"), "cut_first_sentence")).value
    assert rule["jobs"] == ["job-1", "job-2"] and ">= 2" in rule["promoted_by"]
    assert await style_rules(store, "u2") == []                          # memory is per user


async def test_promoted_rules_change_drafts_and_the_critic():
    store = InMemoryStore()
    for job in ("job-1", "job-2"):
        await record_edit(store, "u1", job, BEFORE, NO_WORD)
        await record_edit(store, "u1", job, BEFORE, CUT_FIRST)
    rules = await style_rules(store, "u1")
    assert apply_style(BEFORE, rules).startswith("Your project needs")
    assert style_violations(BEFORE, rules) and not style_violations(NO_WORD, rules)


async def test_outcome_memory_needs_min_samples():
    store = InMemoryStore()
    job = {"job_id": "j1", "title": "Build a RAG chatbot", "skills": ["LangChain"]}
    assert job_category(job) == "ai_ml"
    assert await record_outcome(store, "u1", job, "replied", ["case-01"]) is None
    assert await record_outcome(store, "u1", {**job, "job_id": "j2"}, "ignored", ["case-02"]) is None
    stats = await record_outcome(store, "u1", {**job, "job_id": "j3"}, "interview", ["case-01"])
    assert stats["samples"] == 3 and stats["positive"] == 2 and stats["winning_evidence"][0] == "case-01"
    assert (await outcome_hint(store, "u1", job))["reply_rate"] == 0.67
    await record_outcome(store, "u1", {**job, "job_id": "j3"}, "interview", ["case-01"])   # idempotent per job
    assert (await outcome_hint(store, "u1", job))["samples"] == 3


async def test_user_can_see_and_delete_what_was_learned():
    store = InMemoryStore()
    for job in ("job-1", "job-2"):
        await record_edit(store, "u1", job, BEFORE, CUT_FIRST)
    mem = await list_memory(store, "u1")
    assert [i["key"] for i in mem[STYLE]] == ["cut_first_sentence"]
    assert await delete_memory(store, "u1", STYLE, "cut_first_sentence")
    assert await style_rules(store, "u1") == []
    assert not await delete_memory(store, "u1", "outcome_events", "job-1")      # internal stores not deletable here
    assert (await list_memory(store, "u1"))[STYLE_CANDIDATES]                   # candidate still visible
