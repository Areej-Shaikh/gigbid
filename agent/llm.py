"""One place that talks to LLMs. Every node passes a rule-based fallback, used when:
  - profile is "fake" (tests / offline), or
  - the model fails twice (timeout, bad JSON...)  -> failure handling (C7)
A per-MINUTE provider rate limit is waited out (config llm_rate_limit_retries) instead of falling back:
it clears in seconds. A per-DAY limit falls back at once (waiting would not help).
All providers are OpenAI-compatible (Groq, Ollama, OpenAI), so one client class is enough.
"""
import asyncio
import os
import re
from typing import Callable, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from agent.config import cfg
from agent.tracing import llm_cost, span

T = TypeVar("T", bound=BaseModel)


def _model(name: str) -> ChatOpenAI:
    c = cfg()
    p = c["profiles"][c["profile"]]
    return ChatOpenAI(model=name, base_url=p["base_url"], api_key=os.getenv(p["api_key_env"], "not-set"),
                      temperature=c["temperature"], timeout=c["llm_timeout_s"], max_retries=1)


async def structured(node: str, schema: type[T], system: str, user: str,
                     fallback: Callable[[], T]) -> tuple[T, dict]:
    """Returns (result, info). info = {model, tokens, input_tokens, output_tokens, cost_usd, fallback_used, error}.
    Each call is one trace span carrying the node, model, tokens and USD cost (E3: tokens and cost per node)."""
    c = cfg()
    p = c["profiles"][c["profile"]]
    with span(f"llm.{node}", **{"gigbid.node": node, "gigbid.profile": c["profile"]}) as sp:
        result, info = await _call(node, schema, system, user, fallback, c, p)
        sp.set_attributes({"gigbid.model": info["model"], "gigbid.tokens.input": info["input_tokens"],
                           "gigbid.tokens.output": info["output_tokens"], "gigbid.cost_usd": info["cost_usd"],
                           "gigbid.fallback_used": info["fallback_used"]})
        if info["error"]:
            sp.set_attribute("gigbid.error", info["error"])
        return result, info


def _retry_after(err: Exception) -> float | None:
    """Seconds to wait for a per-minute rate limit (Groq: 'Please try again in 1m2.5s'), None if not one."""
    msg = str(err)
    if "429" not in msg or "per day" in msg or "(TPD)" in msg or "(RPD)" in msg:
        return None
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)(ms|s)", msg)
    if not m:
        return 10.0
    secs = int(m[1] or 0) * 60 + float(m[2]) / (1000 if m[3] == "ms" else 1)
    return min(secs + 0.5, 90.0)


def _info(model: str, usage: dict | None = None, error: str | None = None) -> dict:
    usage = usage or {}
    i, o = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    return {"model": model, "tokens": usage.get("total_tokens", i + o), "input_tokens": i, "output_tokens": o,
            "cost_usd": llm_cost(model, i, o), "fallback_used": model == "rules", "error": error}


async def _call(node, schema, system, user, fallback, c, p):
    if not p.get("models"):
        return fallback(), _info("rules")
    size = c["nodes"].get(node, "small")
    names = [p["models"][size]] + ([p["models"]["fallback"]] if size == "small" else [])
    error = None
    for name in names:
        waits, bad_json = c.get("llm_rate_limit_retries", 2), 1     # bad JSON: one more try on the same model
        while True:
            try:
                res = await _model(name).with_structured_output(schema, include_raw=True).ainvoke(
                    [SystemMessage(system), HumanMessage(user)])
                usage = getattr(res["raw"], "usage_metadata", None) or {}
                if res["parsed"] is not None:
                    return res["parsed"], _info(name, usage)
                error = f"{name}: could not parse output"
                if bad_json:
                    bad_json -= 1
                    continue
            except Exception as e:  # noqa: BLE001 - any provider error -> next model / rules
                error = f"{name}: {type(e).__name__}: {str(e)[:200]}"
                wait = _retry_after(e)
                if wait is not None and waits > 0:
                    waits -= 1
                    await asyncio.sleep(wait)
                    continue
                if bad_json and "Failed to generate JSON" in str(e):
                    bad_json -= 1
                    continue
            break
    return fallback(), _info("rules", error=error)
