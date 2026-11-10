"""Scout: runs saved searches and de-duplicates jobs. Runs in the worker on a schedule (not inside
the bid graph); each NEW job starts its own bid-graph thread."""
import hashlib
import re

from agent.mcp_client import ToolBox


def fingerprint(job: dict) -> str:
    text = re.sub(r"\W+", " ", f"{job['title']} {job.get('description', '')}".lower()).strip()
    return hashlib.sha256(text.encode()).hexdigest()[:16]


async def scout(tb: ToolBox, queries: list[str], seen: set[str], limit: int = 20) -> list[dict]:
    """Returns new, unique jobs. `seen` holds fingerprints already queued (persist it in Postgres/Redis)."""
    new = []
    for q in queries:
        for job in (await tb.call("scout", "search_jobs", query=q, limit=limit))["jobs"]:
            fp = fingerprint(job)
            if fp in seen:
                continue
            seen.add(fp)
            new.append(job)
    return new
