"""GitHub ingestion (B1 + A5) through the official GitHub MCP server (github/github-mcp-server), read-only.

  python -m rag.ingest.github_loader --persona ai_ml_engineer --owner <github-user> --repo my-rag-bot --repo churn-model

Needs GITHUB_PERSONAL_ACCESS_TOKEN (fine-grained, read-only "Contents" on public repos is enough) and Docker
(the server runs as ghcr.io/github/github-mcp-server over stdio; settings in config.yaml -> github_mcp).
For each repo: README plus up to github_mcp.max_code_files small source files from the repo root, written to
data/personas/<persona>/repos/<repo>/. Incremental: a content hash per file is kept in .gigbid_sync.json and unchanged
files are not rewritten; the Portfolio server re-indexes automatically when files change.
No scraping: GitHub's official MCP server and API only.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent.config import cfg

CODE_SUFFIXES = (".py", ".ipynb", ".js", ".ts", ".tsx", ".sql", ".yml", ".yaml", ".toml", ".md")


def _text(res) -> str:
    """File text from a get_file_contents result (text content or an embedded resource)."""
    parts = []
    for c in res.content or []:
        if getattr(c, "text", None):
            parts.append(c.text)
        elif getattr(c, "resource", None) is not None and getattr(c.resource, "text", None):
            parts.append(c.resource.text)
    return "\n".join(parts)


def _entries(res) -> list[dict]:
    """Directory listing from get_file_contents on a folder (JSON list of {name, path, type, size})."""
    for c in res.content or []:
        try:
            data = json.loads(getattr(c, "text", "") or "")
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    return []


async def sync_repo(session: ClientSession, owner: str, repo: str, dest: Path, tool: str = "get_file_contents",
                    max_files: int = 5, max_bytes: int = 20_000) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    state_file = dest / ".gigbid_sync.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    listing = _entries(await session.call_tool(tool, {"owner": owner, "repo": repo, "path": "/"}))
    names = [e["path"] for e in listing if e.get("type") == "file" and e.get("name", "").lower() == "readme.md"]
    names += [e["path"] for e in listing if e.get("type") == "file" and e.get("path", "").endswith(CODE_SUFFIXES)
              and e.get("name", "").lower() != "readme.md" and int(e.get("size") or 0) <= max_bytes][:max_files]
    written, unchanged = [], []
    for path in names:
        text = _text(await session.call_tool(tool, {"owner": owner, "repo": repo, "path": path}))[:max_bytes]
        h = hashlib.sha256(text.encode()).hexdigest()
        if state.get(path) == h:
            unchanged.append(path)
            continue
        (dest / Path(path).name).write_text(text, encoding="utf-8")
        state[path] = h
        written.append(path)
    state_file.write_text(json.dumps(state, indent=1), encoding="utf-8")
    return {"repo": f"{owner}/{repo}", "written": written, "unchanged": unchanged}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", required=True)
    ap.add_argument("--owner", required=True)
    ap.add_argument("--repo", action="append", required=True)
    a = ap.parse_args()
    g = cfg()["github_mcp"]
    if not os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"):
        raise SystemExit("set GITHUB_PERSONAL_ACCESS_TOKEN (read-only) first")
    params = StdioServerParameters(command=g["command"], args=g["args"],
                                   env={**os.environ, "GITHUB_PERSONAL_ACCESS_TOKEN": os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"]})
    async with stdio_client(params) as (read, write), ClientSession(read, write) as s:
        await s.initialize()
        for repo in a.repo:
            dest = Path("data/personas") / a.persona / "repos" / repo
            print(await sync_repo(s, a.owner, repo, dest, g["tools"]["get_file_contents"], g["max_code_files"]))


if __name__ == "__main__":
    asyncio.run(main())
