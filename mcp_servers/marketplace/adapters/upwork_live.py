"""Live adapter (A4): the official Upwork MCP server (https://mcp.upwork.com/mcp, OAuth 2.1) behind the same
marketplace port as GigSim, so the graph cannot tell which marketplace it is using.

- Transport: MCP Streamable HTTP. Auth: the MCP SDK's OAuth 2.1 client (PKCE, dynamic client registration,
  token refresh) with tokens stored ENCRYPTED per user (apps/api/auth/token_store.py). Connect once with
  `python scripts/connect_upwork.py --user <you>`; this adapter never opens a browser and fails clearly if the
  user has not connected.
- Tool names: mapped in config.yaml -> upwork_live.tools (port method -> Upwork tool). They are filled in from the
  real server's tool list, never guessed; an unmapped method raises NotImplementedError naming the config key.
- Writes create DRAFTS only. Upwork requires the user to confirm every proposal and message on Upwork, and GigBid
  only calls these after the user approved in GigBid, so every send is approved twice.
- No scraping, no browser automation, no session cookies. Scheduled reads are throttled by the worker
  (upwork_live.scout_interval_hours).
"""
import json
import os
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession

from agent.config import cfg
from agent.marketplace_port import MarketplaceUnavailable, NotFound

PROVIDER = "upwork"


class UpworkNotConnected(MarketplaceUnavailable):
    """The user has not completed the OAuth flow (or the token was revoked)."""


def _first(d: dict, *keys, default=None):
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return default


def normalise_job(d: dict) -> dict:
    """Map an Upwork job record onto GigBid's job fields (tolerant of naming differences)."""
    budget = d.get("budget") if isinstance(d.get("budget"), dict) else {}
    skills = _first(d, "skills", "requiredSkills", "skill_names", default=[]) or []
    return {
        "job_id": str(_first(d, "job_id", "id", "ciphertext", "jobId", default="")),
        "title": _first(d, "title", default=""),
        "description": _first(d, "description", "snippet", default=""),
        "skills": [s if isinstance(s, str) else _first(s, "name", "prettyName", default=str(s)) for s in skills],
        "budget_type": "hourly" if str(_first(d, "budget_type", "type", "jobType", default="")).lower().startswith("hour") else "fixed",
        "budget_min": _first(d, "budget_min", "hourlyBudgetMin", default=budget.get("min")),
        "budget_max": _first(d, "budget_max", "hourlyBudgetMax", "amount", default=budget.get("max")),
        "client_id": str(_first(d, "client_id", "clientId", "buyerId", default="")),
        "connects_cost": _first(d, "connects_cost", "connectsRequired", default=0),
        "screening_questions": _first(d, "screening_questions", "questions", default=[]) or [],
        "posted_at": _first(d, "posted_at", "createdDateTime", "publishedOn", default=""),
        "source": "upwork",
    }


class UpworkLiveAdapter:
    def __init__(self, user: str | None = None, session: ClientSession | None = None, tool_map: dict | None = None):
        c = cfg().get("upwork_live") or {}
        self.user = user or os.getenv("GIGBID_USER", "demo")
        self.url = c.get("url", "https://mcp.upwork.com/mcp")
        self.tools = dict(tool_map if tool_map is not None else (c.get("tools") or {}))
        self.max_results = int(c.get("max_results", 20))
        self._session, self._stack = session, None

    def __repr__(self) -> str:
        return f"UpworkLiveAdapter(user={self.user!r}, url={self.url!r})"

    # ---------------------------------------------------------------- connection
    async def _ensure(self) -> ClientSession:
        if self._session is not None:
            return self._session
        from mcp.client.auth import OAuthClientProvider
        from mcp.client.streamable_http import streamablehttp_client

        from apps.api.auth.token_store import EncryptedTokenStore, UserTokenStorage
        storage = UserTokenStorage(EncryptedTokenStore(), self.user, PROVIDER)
        if await storage.get_tokens() is None:
            raise UpworkNotConnected(f"Upwork is not connected for user {self.user!r}: run "
                                     f"python scripts/connect_upwork.py --user {self.user}")

        async def no_browser(_url: str) -> None:        # the server must never start an interactive login
            raise UpworkNotConnected("Upwork authorisation expired: reconnect with scripts/connect_upwork.py")

        async def no_callback() -> tuple[str, str | None]:
            raise UpworkNotConnected("Upwork authorisation expired: reconnect with scripts/connect_upwork.py")

        auth = OAuthClientProvider(self.url, client_metadata(), storage, no_browser, no_callback)
        self._stack = AsyncExitStack()
        try:
            read, write, _ = await self._stack.enter_async_context(streamablehttp_client(self.url, auth=auth))
            self._session = await self._stack.enter_async_context(ClientSession(read, write))
            await self._session.initialize()
        except UpworkNotConnected:
            raise
        except Exception as e:  # noqa: BLE001 - network / server errors -> degraded mode in the UI
            raise MarketplaceUnavailable(f"Upwork MCP server unreachable: {type(e).__name__}") from e
        return self._session

    async def aclose(self) -> None:
        if self._stack:
            await self._stack.aclose()

    async def _call(self, method: str, **args) -> Any:
        name = self.tools.get(method)
        if not name:
            raise NotImplementedError(f"Upwork tool for '{method}' is not mapped: set config.yaml -> "
                                      f"upwork_live.tools.{method} (list tools: scripts/connect_upwork.py --list-tools)")
        s = await self._ensure()
        res = await s.call_tool(name, {k: v for k, v in args.items() if v is not None})
        text = " ".join(getattr(c, "text", "") for c in res.content or [])
        if res.isError:
            if "not found" in text.lower() or "404" in text:
                raise NotFound(text[:200])
            raise MarketplaceUnavailable(f"Upwork tool {name} failed: {text[:200]}")
        if res.structuredContent is not None:
            return res.structuredContent
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}

    @staticmethod
    def _items(payload: Any, *keys: str) -> list[dict]:
        if isinstance(payload, list):
            return payload
        for k in (*keys, "items", "results", "data", "result"):
            if isinstance(payload, dict) and isinstance(payload.get(k), list):
                return payload[k]
        return []

    # ---------------------------------------------------------------- read
    async def search_jobs(self, query: str, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        res = await self._call("search_jobs", query=query, limit=min(limit, self.max_results), offset=offset or None)
        return [normalise_job(j) for j in self._items(res, "jobs")]

    async def get_job(self, job_id: str) -> dict[str, Any]:
        res = await self._call("get_job", job_id=job_id)
        return normalise_job(res.get("job", res) if isinstance(res, dict) else {})

    async def get_client(self, client_id: str) -> dict[str, Any]:
        d = await self._call("get_client", client_id=client_id)
        d = d.get("client", d) if isinstance(d, dict) else {}
        return {"client_id": client_id,
                "payment_verified": bool(_first(d, "payment_verified", "paymentVerified", default=False)),
                "total_spent": float(_first(d, "total_spent", "totalSpent", default=0) or 0),
                "hires": int(_first(d, "hires", "totalHires", default=0) or 0),
                "avg_rating": _first(d, "avg_rating", "rating", "feedbackScore"),
                "reviews": int(_first(d, "reviews", "totalReviews", default=0) or 0)}

    async def get_connects_balance(self) -> int:
        d = await self._call("get_connects_balance")
        return int(_first(d, "balance", "connects", "availableConnects", default=0) if isinstance(d, dict) else d)

    async def get_price_stats(self, skill: str) -> dict[str, Any] | None:
        return None        # not offered by Upwork; Pricing falls back to the freelancer's own rate and the client budget

    async def list_messages(self, client_id: str | None = None) -> list[dict[str, Any]]:
        return self._items(await self._call("list_messages", client_id=client_id), "messages")

    async def list_proposals(self) -> list[dict[str, Any]]:
        return self._items(await self._call("list_proposals"), "proposals")

    # ---------------------------------------------------------------- write: DRAFTS only, after approval in GigBid
    async def submit_proposal(self, job_id: str, cover_letter: str, bid_amount: float,
                              screening_answers: list[str], idempotency_key: str) -> dict[str, Any]:
        d = await self._call("create_proposal_draft", job_id=job_id, cover_letter=cover_letter, bid_amount=bid_amount,
                             screening_answers=screening_answers or None, idempotency_key=idempotency_key)
        return {"proposal_id": str(_first(d, "proposal_id", "id", "draftId", default="")) if isinstance(d, dict) else "",
                "status": "draft_on_upwork", "needs_confirmation_on_upwork": True, "connects_cost": None}

    async def send_message(self, client_id: str, text: str, job_id: str | None,
                           idempotency_key: str) -> dict[str, Any]:
        d = await self._call("create_message_draft", client_id=client_id, text=text, job_id=job_id,
                             idempotency_key=idempotency_key)
        return {"message_id": str(_first(d, "message_id", "id", "draftId", default="")) if isinstance(d, dict) else "",
                "status": "draft_on_upwork", "needs_confirmation_on_upwork": True}


def client_metadata():
    from mcp.shared.auth import OAuthClientMetadata
    c = cfg().get("upwork_live") or {}
    return OAuthClientMetadata(client_name="GigBid", redirect_uris=[c.get("redirect_uri", "http://localhost:8765/callback")],
                               grant_types=["authorization_code", "refresh_token"], response_types=["code"],
                               token_endpoint_auth_method="none")
