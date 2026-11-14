"""CV ingestion (B1): PDF or Markdown CV -> one evidence item per section, with metadata.

A PDF CV (cv.pdf in the persona folder, or uploaded later) is split at its headings (Markdown "#" lines, ALL-CAPS
lines, or short lines ending in ":"), so a claim can cite the exact section ("Skills", "Experience", ...) instead of
the whole document. Very long sections are cut into ~chunk_chars pieces at paragraph boundaries.
"""
import re
from pathlib import Path

from pypdf import PdfReader

HEADING = re.compile(r"^(#{1,3}\s+.+|[A-Z][A-Z &/-]{2,40}|[A-Z][\w &/-]{1,40}:)$")


def cv_text(path: Path) -> str:
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "section"


def split_sections(text: str, chunk_chars: int = 1200) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = [("Summary", [])]
    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            sections[-1][1].append("")
            continue
        if HEADING.match(line) and len(line) <= 60:
            sections.append((line.lstrip("#").strip().rstrip(":"), []))
        else:
            sections[-1][1].append(line)
    out = []
    for title, lines in sections:
        body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
        if not body:
            continue
        parts, cur = [], ""
        for para in body.split("\n\n"):
            if cur and len(cur) + len(para) > chunk_chars:
                parts.append(cur)
                cur = ""
            cur = f"{cur}\n\n{para}".strip()
        parts.append(cur)
        out += [(title if len(parts) == 1 else f"{title} ({i + 1})", p) for i, p in enumerate(parts)]
    return out


def cv_items(path: Path, owner: str) -> list[dict]:
    items, used = [], set()
    for title, body in split_sections(cv_text(path)):
        sid = f"{owner}-cv-{_slug(title)}"
        while sid in used:
            sid += "-x"
        used.add(sid)
        items.append({"evidence_id": sid, "type": "cv", "title": f"CV: {title}", "text": body, "source": str(path),
                      "skills": [], "date": "", "client_industry": "", "outcome": "", "project": ""})
    return items
