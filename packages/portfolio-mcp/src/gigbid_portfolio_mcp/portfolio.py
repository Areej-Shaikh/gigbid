"""Load a portfolio folder into evidence items, and search them with BM25.

Folder layout (see README):  cv.md, profile.json, case_studies/*.md (front matter), repos/<name>/*,
reviews.json, proposals.json. Missing optional parts are skipped.
"""
import json
import re
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Plus


def _front_matter(md: str) -> tuple[dict, str]:
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", md, re.S)
    if not m:
        return {}, md
    meta = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        v = v.strip()
        try:
            meta[k.strip()] = json.loads(v)
        except json.JSONDecodeError:
            meta[k.strip()] = v.strip("\"'")
    return meta, m.group(2).strip()


def load_portfolio(base: Path) -> list[dict[str, Any]]:
    base = Path(base)
    if not base.is_dir():
        raise FileNotFoundError(f"portfolio folder not found: {base}")
    owner = base.name
    items: list[dict[str, Any]] = []

    def add(**kw):
        for key, default in (("skills", []), ("date", ""), ("client_industry", ""), ("outcome", ""), ("project", "")):
            kw.setdefault(key, default)
        items.append(kw)

    if (base / "cv.md").exists():
        add(evidence_id=f"{owner}-cv", type="cv", title="CV", text=(base / "cv.md").read_text(encoding="utf-8"),
            source="cv.md")
    for f in sorted((base / "case_studies").glob("*.md")) if (base / "case_studies").is_dir() else []:
        meta, body = _front_matter(f.read_text(encoding="utf-8"))
        add(evidence_id=str(meta.get("id", f.stem)), type="case_study", title=str(meta.get("title", f.stem)), text=body,
            project=str(meta.get("project", "")), skills=list(meta.get("skills", [])), date=str(meta.get("date", "")),
            client_industry=str(meta.get("client_industry", "")), outcome=str(meta.get("outcome", "")),
            source=f"case_studies/{f.name}")
    for d in sorted(p for p in (base / "repos").iterdir() if p.is_dir()) if (base / "repos").is_dir() else []:
        text = "\n\n".join(f.read_text(encoding="utf-8", errors="ignore") for f in sorted(d.iterdir()) if f.is_file())
        add(evidence_id=f"{owner}-repo-{d.name}", type="repo", title=f"Repository: {d.name}", text=text,
            source=f"repos/{d.name}")
    if (base / "reviews.json").exists():
        for r in json.loads((base / "reviews.json").read_text(encoding="utf-8")):
            add(evidence_id=r["id"], type="review", title=f"{r['rating']}-star review: {r['project']}", text=r["text"],
                project=r["project"], date=r.get("date", ""), client_industry=r.get("client_industry", ""),
                outcome=f"{r['rating']} stars", source="reviews.json")
    if (base / "proposals.json").exists():
        for p in json.loads((base / "proposals.json").read_text(encoding="utf-8")):
            add(evidence_id=p["id"], type="proposal", title=f"Past proposal: {p['job_title']}", text=p["text"],
                skills=p.get("job_skills", []), date=p.get("date", ""), client_industry=p.get("client_industry", ""),
                outcome=p.get("outcome", ""), source="proposals.json")
    if not items:
        raise ValueError(f"no evidence found in {base} (expected cv.md, case_studies/, repos/, reviews.json, proposals.json)")
    return items


def load_profile(base: Path, items: list[dict]) -> dict:
    f = Path(base) / "profile.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    skills = sorted({s for i in items for s in i["skills"]})
    return {"headline": Path(base).name, "hourly_rate": 0.0, "skills": skills}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+#.]+", text.lower())


class BM25Index:
    """Keyword retrieval (BM25+). In the GigBid evaluation BM25 gave the best end-to-end bid decisions (see the
    repo's docs/adr/0003) and needs no model download. BM25+ keeps every word's weight positive, so it also
    ranks sensibly in a portfolio of only a handful of items, where plain BM25's IDF goes to zero or below."""
    name = "bm25"

    def __init__(self, items: list[dict[str, Any]]):
        self.items = items
        self.docs = [_tokens(f"{i['title']} {' '.join(i['skills'])} {i['text']}") for i in items]
        self.bm25 = BM25Plus(self.docs)

    def search(self, query: str, k: int = 5, filters: dict | None = None) -> list[tuple[dict, float]]:
        q = _tokens(query)
        scores = self.bm25.get_scores(q)
        # BM25+ gives every document a small positive score, so keep only items sharing a word with the query
        overlap = [len(set(q) & set(d)) for d in self.docs]
        out = []
        for item, s, o in sorted(zip(self.items, scores, overlap), key=lambda x: (-x[1], -x[2])):
            if o == 0:
                continue
            if filters and not _matches(item, filters):
                continue
            out.append((item, float(s)))
            if len(out) == k:
                break
        return out


def _matches(item: dict, f: dict) -> bool:
    if f.get("types") and item["type"] not in f["types"]:
        return False
    if f.get("outcomes") and item["outcome"] not in f["outcomes"]:
        return False
    if f.get("since") and item["date"] and item["date"] < f["since"]:
        return False
    return True
