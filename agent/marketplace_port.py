"""The ONE interface every part of GigBid uses to reach a marketplace (requirement R1).

Two adapters implement it:
  - GigSimAdapter      -> our mock marketplace (development + grading)
  - UpworkLiveAdapter  -> official Upwork MCP server (live mode)
Switch with the MARKETPLACE_MODE environment variable: "gigsim" (default) or "upwork".
The agents never know which one is behind the port.
"""
import os
from typing import Any, Protocol


class MarketplaceUnavailable(Exception):
    """Marketplace is down or keeps failing after retries -> UI shows degraded mode."""


class NotFound(Exception):
    """Job / client does not exist."""


class MarketplacePort(Protocol):
    # ---- read ----
    async def search_jobs(self, query: str, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]: ...
    async def get_job(self, job_id: str) -> dict[str, Any]: ...
    async def get_client(self, client_id: str) -> dict[str, Any]: ...
    async def get_connects_balance(self) -> int: ...
    async def get_price_stats(self, skill: str) -> dict[str, Any] | None: ...
    async def list_messages(self, client_id: str | None = None) -> list[dict[str, Any]]: ...

    # ---- write (only ever called after human approval) ----
    async def submit_proposal(self, job_id: str, cover_letter: str, bid_amount: float,
                              screening_answers: list[str], idempotency_key: str) -> dict[str, Any]: ...
    async def send_message(self, client_id: str, text: str, job_id: str | None,
                           idempotency_key: str) -> dict[str, Any]: ...


def get_marketplace() -> MarketplacePort:
    mode = os.getenv("MARKETPLACE_MODE", "gigsim").lower()
    if mode == "gigsim":
        from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
        return GigSimAdapter()
    if mode == "upwork":
        from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter
        return UpworkLiveAdapter()
    raise ValueError(f"Unknown MARKETPLACE_MODE: {mode}")
