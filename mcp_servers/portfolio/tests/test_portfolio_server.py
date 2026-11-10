"""Portfolio MCP server tests (in-memory MCP client).  Run: python -m pytest mcp_servers/portfolio/tests -q
Needs persona data: python scripts/generate_personas.py
"""
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.portfolio import server

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def persona(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_PERSONA", "ai_ml_engineer")


async def test_tools_resources_prompts_listed():
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        assert set(tools) == {"search_evidence", "get_case_study", "list_skills"}
        assert all(t.annotations.readOnlyHint for t in tools.values())
        templates = [t.uriTemplate for t in (await s.list_resource_templates()).resourceTemplates]
        assert "portfolio://case/{case_id}" in templates and "portfolio://proposal/{proposal_id}" in templates
        prompts = [p.name for p in (await s.list_prompts()).prompts]
        assert "answer_screening_question" in prompts


async def test_search_finds_relevant_evidence():
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as s:
        r = (await s.call_tool("search_evidence", {"requirement": "RAG chatbot with citations", "k": 3})).structuredContent
        assert len(r["results"]) == 3
        assert any("RAG" in e["skills"] or "Q&A" in e["title"] for e in r["results"])


async def test_filters_by_type_and_outcome():
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as s:
        r = (await s.call_tool("search_evidence", {"requirement": "Python", "k": 5, "types": ["proposal"],
                                                    "outcomes": ["won"]})).structuredContent
        assert r["results"] and all(e["type"] == "proposal" and e["outcome"] == "won" for e in r["results"])


async def test_get_case_study_and_resource():
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as s:
        c = (await s.call_tool("get_case_study", {"evidence_id": "ai_ml_engineer-case-01"})).structuredContent
        assert c["text"]
        res = await s.read_resource("portfolio://case/ai_ml_engineer-case-01")
        assert c["title"] in res.contents[0].text


async def test_unknown_id_is_error():
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as s:
        r = await s.call_tool("get_case_study", {"evidence_id": "nope"})
        assert r.isError
