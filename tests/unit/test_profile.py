"""Onboarding profile (D): stored per user, persona travels to the Portfolio server, regenerate-paragraph fallback."""
import asyncio

import pytest
from langgraph.store.memory import InMemoryStore
from mcp.shared.memory import create_connected_server_and_client_session

from agent.mcp_client import ToolBox
from agent.profile import current_persona, get_profile, personas, save_profile
from apps.api.routers.runs import _rule_paragraph
from mcp_servers.portfolio import server as portfolio


def test_profile_is_per_user_with_config_defaults():
    async def go():
        store = InMemoryStore()
        await save_profile(store, "alice", {"persona": "data_analyst", "min_hourly_rate": 40, "onboarded": True})
        a, b = await get_profile(store, "alice"), await get_profile(store, "bob")
        assert a["persona"] == "data_analyst" and a["min_hourly_rate"] == 40 and a["onboarded"]
        assert b["onboarded"] is False and b["min_hourly_rate"] == 25          # bob still has the defaults
        with pytest.raises(ValueError):
            await save_profile(store, "alice", {"persona": "../etc"})
    asyncio.run(go())
    assert {"ai_ml_engineer", "data_analyst", "fullstack_developer"} <= set(personas())


def test_chosen_persona_reaches_the_portfolio_server(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_PERSONA", "ai_ml_engineer")

    async def go():
        async with create_connected_server_and_client_session(portfolio.mcp._mcp_server) as s:
            tb = await ToolBox({"portfolio": s}).init()
            default = await tb.call("fit", "list_skills")
            token = current_persona.set("data_analyst")      # what the run manager sets from the user's profile
            try:
                chosen = await tb.call("fit", "list_skills")
            finally:
                current_persona.reset(token)
            return default, chosen
    default, chosen = asyncio.run(go())
    assert default["persona"] == "ai_ml_engineer" and chosen["persona"] == "data_analyst"


def test_regenerate_without_llm_uses_evidence_not_yet_cited():
    ev = {"a-1": {"title": "Churn model", "text": "Built a churn model. AUC rose from 0.71 to 0.83."},
          "a-2": {"title": "RAG bot", "text": "Built a RAG bot over 150 contracts."}}
    out = _rule_paragraph("I built a churn model [a-1].", ev)
    assert "[a-2]" in out.paragraph and "150 contracts" in out.paragraph
