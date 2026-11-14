"""Explicit promotion rules (R7): the ONLY way knowledge enters long-term memory.

Style memory (from the user's edits to drafts):
  1. Every edit is turned into candidate patterns (cut the first sentence, avoid a word, keep it shorter).
     Raw draft text is never stored, only the pattern and the job ids it was seen on.
  2. A candidate is PROMOTED to a style rule once it is seen in edits on `promote_after_jobs`
     DIFFERENT jobs (config: memory.style). One-off edits never become rules.

Outcome memory (what won or got replies, per job category):
  1. Each known outcome is stored as one small event (category, outcome label, cited evidence ids).
  2. A category's stats are PROMOTED once it has `min_samples` outcomes (config: memory.outcome).

All thresholds live in config.yaml, so they can change without code changes.
"""
import difflib
import re
import time

from langgraph.store.base import BaseStore

from agent.config import cfg
from agent.memory.store import OUTCOME, OUTCOME_EVENTS, STYLE, STYLE_CANDIDATES, ns

CITE = re.compile(r"\[[A-Za-z0-9_\-]+\]")
STOP = set("the a an and or for with from that this into over your our was were have has had are is to of in on at by "
           "which who what when where while about than then them they their there these those also very just will "
           "would could should can may might been being it its i me my we us you".split())


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z'-]+", CITE.sub("", text).lower())


def edit_candidates(before: str, after: str) -> list[dict]:
    """Turn one edit into candidate style patterns: [{key, rule, kind}]. Pure function, easy to test."""
    c = cfg()["memory"]["style"]
    out = []
    b_sent = _sentences(before)
    cut_first = len(b_sent) > 1 and b_sent[0] not in after and b_sent[1][:40] in after
    if cut_first:
        out.append({"key": "cut_first_sentence", "kind": "structure",
                    "rule": "Cut the opening sentence: start directly with the client's problem."})
    bw, aw = _words(before), _words(after)
    sm = difflib.SequenceMatcher(a=bw, b=aw, autojunk=False)
    if sm.ratio() >= c["min_similarity"]:          # a light edit, not a rewrite: deleted words are deliberate
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            removed = bw[i1:i2]
            if op in ("delete", "replace") and 0 < len(removed) <= c["max_removed_words"]:
                for w in removed:
                    if len(w) > 3 and w not in STOP and w not in aw:
                        out.append({"key": f"avoid:{w}", "kind": "word", "word": w,
                                    "rule": f"Never use the word \"{w}\"."})
    base = _words(" ".join(b_sent[1:])) if cut_first else bw     # cutting the opener is not "shorter" twice
    if base and len(aw) < c["shorter_ratio"] * len(base):
        out.append({"key": "shorter", "kind": "length", "target_words": len(aw),
                    "rule": f"Keep the letter short (about {len(aw)} words or fewer)."})
    seen, uniq = set(), []
    for x in out:
        if x["key"] not in seen:
            seen.add(x["key"]); uniq.append(x)
    return uniq


async def record_edit(store: BaseStore, user: str, job_id: str, before: str, after: str) -> list[str]:
    """Record an edit; returns the keys of style rules PROMOTED by this edit."""
    need = cfg()["memory"]["style"]["promote_after_jobs"]
    promoted = []
    for cand in edit_candidates(before, after):
        item = await store.aget(ns(STYLE_CANDIDATES, user), cand["key"])
        jobs = sorted(set((item.value["jobs"] if item else []) + [job_id]))
        await store.aput(ns(STYLE_CANDIDATES, user), cand["key"], {**cand, "jobs": jobs, "count": len(jobs)})
        already = await store.aget(ns(STYLE, user), cand["key"])
        if len(jobs) >= need:                                        # <- THE promotion rule
            await store.aput(ns(STYLE, user), cand["key"],
                             {**cand, "jobs": jobs, "count": len(jobs),
                              "promoted_by": f"seen in edits on {len(jobs)} different jobs (rule: >= {need})",
                              "promoted_at": (already.value.get("promoted_at") if already else None)
                              or time.strftime("%Y-%m-%dT%H:%M:%S")})
            if not already:
                promoted.append(cand["key"])
    return promoted


async def style_rules(store: BaseStore | None, user: str) -> list[dict]:
    if store is None:
        return []
    return [i.value | {"key": i.key} for i in await store.asearch(ns(STYLE, user), limit=50)]


def apply_style(text: str, rules: list[dict]) -> str:
    """Deterministic part of style memory, used on rule-based drafts (no LLM to instruct)."""
    keys = {r["key"] for r in rules}
    sents = _sentences(text)
    if "cut_first_sentence" in keys and len(sents) > 1:
        sents = sents[1:]
    return " ".join(sents)


def style_violations(text: str, rules: list[dict]) -> list[str]:
    """Critic check: a draft must not use a word the user taught GigBid to avoid."""
    words = set(_words(text))
    return [f"uses \"{r['word']}\" (style memory: you removed it from earlier drafts)"
            for r in rules if r.get("kind") == "word" and r["word"] in words]


def job_category(job: dict) -> str:
    text = f" {job.get('title', '')} {' '.join(job.get('skills') or [])} ".lower()
    for cat, keywords in cfg()["memory"]["categories"].items():
        if any(k in text for k in keywords):
            return cat
    return "other"


async def record_outcome(store: BaseStore, user: str, job: dict, outcome: str,
                         evidence_ids: list[str] | None = None) -> dict | None:
    """Record one job outcome (replied / interview / hired / ignored / rejected).
    Returns the promoted category stats if this outcome made the category eligible, else None."""
    c = cfg()["memory"]["outcome"]
    cat = job_category(job)
    await store.aput(ns(OUTCOME_EVENTS, user), job["job_id"],
                     {"category": cat, "outcome": outcome, "evidence_ids": evidence_ids or []})
    events = [i.value for i in await store.asearch(ns(OUTCOME_EVENTS, user), filter={"category": cat}, limit=1000)]
    if len(events) < c["min_samples"]:                               # <- THE promotion rule
        return None
    good = [e for e in events if e["outcome"] in c["positive"]]
    wins: dict[str, int] = {}
    for e in good:
        for i in e["evidence_ids"]:
            wins[i] = wins.get(i, 0) + 1
    stats = {"category": cat, "samples": len(events), "positive": len(good),
             "reply_rate": round(len(good) / len(events), 2),
             "winning_evidence": [i for i, _ in sorted(wins.items(), key=lambda x: -x[1])[:5]],
             "promoted_by": f"{len(events)} outcomes in category (rule: >= {c['min_samples']})"}
    await store.aput(ns(OUTCOME, user), cat, stats)
    return stats


async def outcome_hint(store: BaseStore | None, user: str, job: dict) -> dict | None:
    if store is None:
        return None
    item = await store.aget(ns(OUTCOME, user), job_category(job))
    return item.value if item else None
