"""The packaged server works on its bundled sample and on a user's own folder, through a real MCP client."""
import json

import anyio
from gigbid_portfolio_mcp import server
from mcp.shared.memory import create_connected_server_and_client_session


def call(tool: str, args: dict | None = None):
    async def go():
        async with create_connected_server_and_client_session(server.mcp._mcp_server) as s:
            listed = {t.name for t in (await s.list_tools()).tools}
            res = await s.call_tool(tool, args or {})
            return listed, res
    return anyio.run(go)


def test_tools_on_bundled_sample(monkeypatch):
    monkeypatch.delenv("PORTFOLIO_DIR", raising=False)
    listed, res = call("search_evidence", {"requirement": "RAG chatbot with citations", "k": 3})
    assert listed == {"search_evidence", "get_case_study", "list_skills"}
    out = res.structuredContent
    assert out["retriever"] == "bm25" and 1 <= len(out["results"]) <= 3
    first = out["results"][0]["evidence_id"]
    _, case = call("get_case_study", {"evidence_id": first})
    assert case.structuredContent["evidence_id"] == first


def test_unknown_id_is_a_tool_error(monkeypatch):
    monkeypatch.delenv("PORTFOLIO_DIR", raising=False)
    _, res = call("get_case_study", {"evidence_id": "nope"})
    assert res.isError and "not_found" in res.content[0].text


def test_own_portfolio_folder(tmp_path, monkeypatch):
    (tmp_path / "case_studies").mkdir()
    (tmp_path / "case_studies" / "shop.md").write_text(
        '---\nid: "me-case-1"\ntitle: "Shopify store migration"\nproject: "Store"\nskills: ["Shopify", "Liquid"]\n'
        'date: "2026-03-01"\nclient_industry: "retail"\noutcome: "delivered"\n---\nMigrated 1,200 products to Shopify.\n',
        encoding="utf-8")
    (tmp_path / "reviews.json").write_text(json.dumps([{"id": "me-rev-1", "rating": 5, "project": "Store",
                                                         "text": "Fast Shopify work", "date": "2026-03-10"}]), encoding="utf-8")
    monkeypatch.setenv("PORTFOLIO_DIR", str(tmp_path))
    _, res = call("search_evidence", {"requirement": "Shopify migration"})
    assert [r["evidence_id"] for r in res.structuredContent["results"]][0] == "me-case-1"
    _, skills = call("list_skills")
    assert {s["skill"] for s in skills.structuredContent["skills"]} >= {"Shopify", "Liquid"}
