"""Load one persona's portfolio into a flat list of evidence items (with metadata on every item).

Types: cv, case_study, repo, review, proposal.
TODO (Part B1): PDF CVs, GitHub repos via the GitHub MCP server, chunking, incremental re-index.
"""
import json
import re
from pathlib import Path
from typing import Any

PERSONAS_DIR = Path("data/personas")


def _front_matter(md: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", md, re.S)
    if not m:
        return {}, md
    meta = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        meta[k.strip()] = json.loads(v.strip())
    return meta, m.group(2).strip()


def load_portfolio(persona_id: str, root: Path = PERSONAS_DIR) -> list[dict[str, Any]]:
    base = root / persona_id
    if not base.exists():
        raise FileNotFoundError(f"No persona folder {base}. Run: python scripts/generate_personas.py")
    items = []

    def add(**kw):
        kw.setdefault("skills", [])
        kw.setdefault("date", "")
        kw.setdefault("client_industry", "")
        kw.setdefault("outcome", "")
        kw.setdefault("project", "")
        kw["persona"] = persona_id
        items.append(kw)

    cv = (base / "cv.md").read_text(encoding="utf-8")
    add(evidence_id=f"{persona_id}-cv", type="cv", title="CV", text=cv, source=str(base / "cv.md"))

    for f in sorted((base / "case_studies").glob("*.md")):
        meta, body = _front_matter(f.read_text(encoding="utf-8"))
        add(evidence_id=meta["id"], type="case_study", title=meta["title"], text=body, project=meta["project"],
            skills=meta["skills"], date=meta["date"], client_industry=meta["client_industry"],
            outcome=meta["outcome"], source=str(f))

    for d in sorted(p for p in (base / "repos").iterdir() if p.is_dir()):
        text = "\n\n".join(f.read_text(encoding="utf-8") for f in sorted(d.iterdir()) if f.is_file())
        add(evidence_id=f"{persona_id}-repo-{d.name}", type="repo", title=f"Repository: {d.name}", text=text,
            source=str(d))

    for r in json.loads((base / "reviews.json").read_text(encoding="utf-8")):
        add(evidence_id=r["id"], type="review", title=f"{r['rating']}-star review: {r['project']}",
            text=r["text"], project=r["project"], date=r["date"], client_industry=r["client_industry"],
            outcome=f"{r['rating']} stars", source=str(base / "reviews.json"))

    for p in json.loads((base / "proposals.json").read_text(encoding="utf-8")):
        add(evidence_id=p["id"], type="proposal", title=f"Past proposal: {p['job_title']}", text=p["text"],
            skills=p["job_skills"], date=p["date"], client_industry=p["client_industry"], outcome=p["outcome"],
            source=str(base / "proposals.json"))
    return items


def load_profile(persona_id: str, root: Path = PERSONAS_DIR) -> dict:
    return json.loads((root / persona_id / "profile.json").read_text(encoding="utf-8"))
