"""GigSim adapter: talks to the mock marketplace over HTTP, with retries and backoff."""
import asyncio
import os
import random
from typing import Any

import httpx

from agent.marketplace_port import MarketplaceUnavailable, NotFound

RETRY_STATUS = {429, 500, 502, 503, 504}


class GigSimAdapter:
    def __init__(self, base_url: str | None = None, transport: httpx.AsyncBaseTransport | None = None,
                 max_retries: int = 4, timeout: float = 10.0):
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(
            base_url=base_url or os.getenv("GIGSIM_URL", "http://127.0.0.1:8001"),
            timeout=timeout, transport=transport)

    async def _request(self, method: str, path: str, **kw) -> Any:
        last_error = "unknown error"
        for attempt in range(self.max_retries + 1):
            wait = 0.5 * 2 ** attempt + random.uniform(0, 0.3)  # exponential backoff + jitter
            try:
                r = await self.client.request(method, path, **kw)
            except httpx.TransportError as e:  # connection refused, timeout...
                last_error = f"{type(e).__name__}: {e}"
            else:
                if r.status_code == 404:
                    raise NotFound(r.json().get("detail", "not found"))
                if r.status_code in RETRY_STATUS:
                    last_error = f"HTTP {r.status_code}"
                    if r.headers.get("Retry-After"):
                        wait = float(r.headers["Retry-After"])
                else:
                    r.raise_for_status()  # other 4xx = our bug, don't retry
                    return r.json()
            if attempt < self.max_retries:
                await asyncio.sleep(min(wait, 10))
        raise MarketplaceUnavailable(f"GigSim unavailable after {self.max_retries + 1} tries ({last_error})")

    # ---- read ----
    async def search_jobs(self, query: str, limit: int = 20, offset: int = 0):
        return await self._request("GET", "/jobs", params={"q": query, "limit": limit, "offset": offset})

    async def get_job(self, job_id: str):
        return await self._request("GET", f"/jobs/{job_id}")

    async def get_client(self, client_id: str):
        return await self._request("GET", f"/clients/{client_id}")

    async def get_connects_balance(self) -> int:
        return (await self._request("GET", "/connects"))["balance"]

    async def get_price_stats(self, skill: str):
        try:
            return await self._request("GET", "/stats/prices", params={"skill": skill})
        except NotFound:
            return None

    async def list_messages(self, client_id: str | None = None):
        return await self._request("GET", "/messages", params={"client_id": client_id} if client_id else {})

    async def list_proposals(self):
        return await self._request("GET", "/proposals")

    # ---- write ----
    async def submit_proposal(self, job_id, cover_letter, bid_amount, screening_answers, idempotency_key):
        return await self._request(
            "POST", "/proposals", headers={"Idempotency-Key": idempotency_key},
            json={"job_id": job_id, "cover_letter": cover_letter, "bid_amount": bid_amount,
                  "screening_answers": screening_answers})

    async def send_message(self, client_id, text, job_id, idempotency_key):
        return await self._request(
            "POST", "/messages", headers={"Idempotency-Key": idempotency_key},
            json={"client_id": client_id, "job_id": job_id, "text": text})
