"""Live Upwork adapter (A4) and encrypted token store (E4), tested against a fake Upwork-like MCP server.
No network: the real server needs an approved Upwork account, so the mapping is exercised in memory."""
import asyncio
import json

import pytest
from cryptography.fernet import Fernet
from mcp.server.fastmcp import FastMCP
from mcp.shared.auth import OAuthToken
from mcp.shared.memory import create_connected_server_and_client_session

from apps.api.auth.token_store import EncryptedTokenStore, TokenStoreError, UserTokenStorage
from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter, UpworkNotConnected

KEY = Fernet.generate_key().decode()

# ---------------------------------------------------------------- a fake server with Upwork-style names and shapes
fake = FastMCP("fake-upwork")
drafts: list[dict] = []


@fake.tool()
def find_jobs(query: str, limit: int = 10) -> dict:
    return {"jobs": [{"ciphertext": "~01abc", "title": "RAG chatbot", "description": "Build a RAG bot",
                      "requiredSkills": [{"prettyName": "LangChain"}, {"prettyName": "Python"}],
                      "jobType": "HOURLY", "hourlyBudgetMin": 30, "hourlyBudgetMax": 60, "buyerId": "b1"}]}


@fake.tool()
def create_proposal(job_id: str, cover_letter: str, bid_amount: float, idempotency_key: str) -> dict:
    drafts.append({"job_id": job_id, "key": idempotency_key})
    return {"draftId": f"d-{len(drafts)}", "state": "DRAFT"}


MAP = {"search_jobs": "find_jobs", "create_proposal_draft": "create_proposal"}


def with_adapter(fn):
    async def go():
        async with create_connected_server_and_client_session(fake._mcp_server) as s:
            try:
                return await fn(UpworkLiveAdapter(user="alice", session=s, tool_map=MAP))
            except Exception as e:  # noqa: BLE001 - re-raised outside the session's task group (no ExceptionGroup)
                return e
    out = asyncio.run(go())
    if isinstance(out, Exception):
        raise out
    return out


def test_jobs_are_mapped_onto_the_port():
    jobs = with_adapter(lambda a: a.search_jobs("rag"))
    assert jobs[0]["job_id"] == "~01abc" and jobs[0]["skills"] == ["LangChain", "Python"]
    assert jobs[0]["budget_type"] == "hourly" and jobs[0]["budget_max"] == 60 and jobs[0]["source"] == "upwork"


def test_writes_only_create_drafts_that_need_confirmation_on_upwork():
    drafts.clear()
    res = with_adapter(lambda a: a.submit_proposal("~01abc", "letter", 40, [], "thread-1-submit"))
    assert res["status"] == "draft_on_upwork" and res["needs_confirmation_on_upwork"] is True
    assert drafts == [{"job_id": "~01abc", "key": "thread-1-submit"}]


def test_unmapped_tool_fails_clearly():
    with pytest.raises(NotImplementedError, match="upwork_live.tools.get_job"):
        with_adapter(lambda a: a.get_job("x"))


def test_not_connected_user_gets_degraded_mode_not_a_login(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", KEY)
    monkeypatch.setenv("TOKEN_STORE_PATH", str(tmp_path / "t.json"))
    import apps.api.auth.token_store as ts
    monkeypatch.setattr(ts, "DEFAULT_PATH", tmp_path / "t.json")
    with pytest.raises(UpworkNotConnected):
        asyncio.run(UpworkLiveAdapter(user="nobody", tool_map=MAP).search_jobs("rag"))


# ---------------------------------------------------------------- encrypted, tenant-scoped token store
def test_tokens_are_encrypted_at_rest_and_scoped_per_user(tmp_path):
    store = EncryptedTokenStore(tmp_path / "tokens.json", key=KEY)
    alice = UserTokenStorage(store, "alice", "upwork")
    asyncio.run(alice.set_tokens(OAuthToken(access_token="SECRET-ACCESS-123", token_type="Bearer", refresh_token="R-456")))
    raw = (tmp_path / "tokens.json").read_text(encoding="utf-8")
    assert "SECRET-ACCESS-123" not in raw and "R-456" not in raw          # ciphertext only on disk
    assert asyncio.run(alice.get_tokens()).access_token == "SECRET-ACCESS-123"
    assert asyncio.run(UserTokenStorage(store, "bob", "upwork").get_tokens()) is None   # other tenant sees nothing
    assert "SECRET" not in repr(store) + repr(alice)
    with pytest.raises(TokenStoreError):                                    # wrong key cannot read it
        EncryptedTokenStore(tmp_path / "tokens.json", key=Fernet.generate_key()).get("alice", "upwork", "tokens")
    store.delete("alice", "upwork")
    assert json.loads((tmp_path / "tokens.json").read_text(encoding="utf-8")) == {}


def test_refuses_to_store_without_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv("TOKEN_ENCRYPTION_KEY", raising=False)
    with pytest.raises(TokenStoreError):
        EncryptedTokenStore(tmp_path / "t.json")
