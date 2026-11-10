"""One place that talks to LLMs. Every node passes a rule-based fallback, used when:
  - profile is "fake" (tests / offline), or
  - the model fails twice (timeout, bad JSON...)  -> failure handling (C7)
All providers are OpenAI-compatible (Groq, Ollama, OpenAI), so one client class is enough.
"""
import os
from typing import Callable, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from agent.config import cfg

T = TypeVar("T", bound=BaseModel)


def _model(name: str) -> ChatOpenAI:
    c = cfg()
    p = c["profiles"][c["profile"]]
    return ChatOpenAI(model=name, base_url=p["base_url"], api_key=os.getenv(p["api_key_env"], "not-set"),
                      temperature=c["temperature"], timeout=c["llm_timeout_s"], max_retries=1)


async def structured(node: str, schema: type[T], system: str, user: str,
                     fallback: Callable[[], T]) -> tuple[T, dict]:
    """Returns (result, info). info = {model, tokens, fallback_used, error}."""
    c = cfg()
    p = c["profiles"][c["profile"]]
    if not p.get("models"):
        return fallback(), {"model": "rules", "tokens": 0, "fallback_used": True, "error": None}
    size = c["nodes"].get(node, "small")
    names = [p["models"][size]] + ([p["models"]["fallback"]] if size == "small" else [])
    error = None
    for name in names:
        try:
            res = await _model(name).with_structured_output(schema, include_raw=True).ainvoke(
                [SystemMessage(system), HumanMessage(user)])
            usage = getattr(res["raw"], "usage_metadata", None) or {}
            if res["parsed"] is not None:
                return res["parsed"], {"model": name, "tokens": usage.get("total_tokens", 0),
                                       "fallback_used": False, "error": None}
            error = f"{name}: could not parse output"
        except Exception as e:  # noqa: BLE001 - any provider error -> next model / rules
            error = f"{name}: {type(e).__name__}: {str(e)[:200]}"
    return fallback(), {"model": "rules", "tokens": 0, "fallback_used": True, "error": error}
