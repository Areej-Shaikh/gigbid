"""Connect a GigBid user to the official Upwork MCP server (OAuth 2.1 with PKCE), once.

  python scripts/connect_upwork.py --user demo                 # opens Upwork's consent page in your browser
  python scripts/connect_upwork.py --user demo --list-tools    # after connecting: show the server's real tool names
  python scripts/connect_upwork.py --user demo --disconnect

Needs TOKEN_ENCRYPTION_KEY in .env. Tokens are written only to the encrypted token store (never printed).
Copy the tool names from --list-tools into config.yaml -> upwork_live.tools, then set MARKETPLACE_MODE=upwork.
"""
import argparse
import asyncio
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from mcp import ClientSession  # noqa: E402
from mcp.client.auth import OAuthClientProvider  # noqa: E402
from mcp.client.streamable_http import streamablehttp_client  # noqa: E402

from agent.config import cfg  # noqa: E402
from apps.api.auth.token_store import EncryptedTokenStore, UserTokenStorage  # noqa: E402
from mcp_servers.marketplace.adapters.upwork_live import PROVIDER, client_metadata  # noqa: E402


def wait_for_callback(port: int, timeout: float = 300) -> tuple[str, str | None]:
    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            result["code"], result["state"] = (q.get("code") or [None])[0], (q.get("state") or [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h3>GigBid is connected to Upwork. You can close this tab.</h3>")

        def log_message(self, *a):            # keep the authorisation code out of the console
            pass

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = timeout
    Thread(target=server.handle_request, daemon=True).start()
    import time
    t0 = time.time()
    while "code" not in result and time.time() - t0 < timeout:
        time.sleep(0.2)
    server.server_close()
    if not result.get("code"):
        raise SystemExit("no authorisation code received (timed out or denied)")
    return result["code"], result["state"]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True)
    ap.add_argument("--list-tools", action="store_true")
    ap.add_argument("--disconnect", action="store_true")
    a = ap.parse_args()
    store = EncryptedTokenStore()
    if a.disconnect:
        store.delete(a.user, PROVIDER)
        return print(f"disconnected {a.user} from Upwork (tokens deleted)")
    c = cfg()["upwork_live"]
    port = urlparse(c["redirect_uri"]).port or 8765

    async def open_browser(url: str) -> None:
        print("Opening Upwork's consent page in your browser...")
        webbrowser.open(url)

    async def callback() -> tuple[str, str | None]:
        return await asyncio.to_thread(wait_for_callback, port)

    auth = OAuthClientProvider(c["url"], client_metadata(), UserTokenStorage(store, a.user, PROVIDER), open_browser, callback)
    async with streamablehttp_client(c["url"], auth=auth) as (read, write, _), ClientSession(read, write) as s:
        await s.initialize()
        print(f"connected: user {a.user!r} -> {c['url']} (tokens stored encrypted)")
        if a.list_tools:
            for t in (await s.list_tools()).tools:
                hints = t.annotations.model_dump(exclude_none=True) if t.annotations else {}
                print(f"  {t.name:40s} {hints}  {(t.description or '').splitlines()[0][:80] if t.description else ''}")


if __name__ == "__main__":
    asyncio.run(main())
