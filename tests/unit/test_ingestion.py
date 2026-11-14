"""B1 ingestion: PDF CV -> section items; GitHub repo sync (incremental) through an MCP session; re-index on change."""
import asyncio
import json

from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from rag.ingest.cv_loader import cv_items, split_sections
from rag.ingest.github_loader import sync_repo
from rag.ingest.portfolio_loader import portfolio_version


def tiny_pdf(lines: list[str]) -> bytes:
    """A minimal valid one-page PDF with one text line per entry (no PDF library needed)."""
    text = "BT /F1 11 Tf 50 780 Td 14 TL " + " ".join(f"({ln}) Tj T*" for ln in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(text)} >>\nstream\n{text}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF"
    return out.encode("latin-1")


def test_pdf_cv_becomes_one_item_per_section(tmp_path):
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(tiny_pdf(["Jane Doe", "SKILLS", "Python, LangGraph, FastAPI", "EXPERIENCE",
                              "Built a RAG assistant for 150 contracts", "EDUCATION", "BS Computer Science"]))
    items = cv_items(pdf, "jane")
    titles = [i["title"] for i in items]
    assert "CV: SKILLS" in titles and "CV: EXPERIENCE" in titles
    exp = next(i for i in items if i["title"] == "CV: EXPERIENCE")
    assert "RAG assistant" in exp["text"] and exp["evidence_id"] == "jane-cv-experience" and exp["type"] == "cv"


def test_markdown_headings_split_too():
    secs = dict(split_sections("# Name\n\nintro\n\n## Skills\n\nPython\n\n## Projects\n\nA chatbot"))
    assert secs["Skills"] == "Python" and secs["Projects"] == "A chatbot"


# ---------------------------------------------------------------- GitHub MCP (fake server with the official tool name)
gh = FastMCP("fake-github")
FILES = {"README.md": "# churn-model\nGradient boosting churn model, AUC 0.91.", "train.py": "print('train')"}


@gh.tool()
def get_file_contents(owner: str, repo: str, path: str = "/") -> str:
    if path in ("/", ""):
        return json.dumps([{"name": n, "path": n, "type": "file", "size": len(t)} for n, t in FILES.items()] +
                          [{"name": "data", "path": "data", "type": "dir"}])
    return FILES[path]


def test_github_repo_sync_is_incremental(tmp_path):
    async def go():
        async with create_connected_server_and_client_session(gh._mcp_server) as s:
            first = await sync_repo(s, "me", "churn-model", tmp_path / "churn-model")
            second = await sync_repo(s, "me", "churn-model", tmp_path / "churn-model")
            FILES["train.py"] = "print('train v2')"
            third = await sync_repo(s, "me", "churn-model", tmp_path / "churn-model")
            return first, second, third
    first, second, third = asyncio.run(go())
    assert sorted(first["written"]) == ["README.md", "train.py"]
    assert second["written"] == [] and sorted(second["unchanged"]) == ["README.md", "train.py"]
    assert third["written"] == ["train.py"]
    assert "AUC 0.91" in (tmp_path / "churn-model" / "README.md").read_text(encoding="utf-8")


def test_portfolio_version_changes_when_work_is_added(tmp_path):
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "cv.md").write_text("cv", encoding="utf-8")
    v1 = portfolio_version("p", tmp_path)
    (tmp_path / "p" / "case.md").write_text("new case", encoding="utf-8")
    assert portfolio_version("p", tmp_path) != v1
