"""Onboarding (D): the signed-in user's profile, marketplace connection and portfolio uploads."""
import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile

from agent.profile import PERSONAS_DIR, get_profile, personas, save_profile
from apps.api.auth.security import User
from apps.api.schemas.models import PortfolioUpload, ProfileIn, ProfileOut

router = APIRouter(prefix="/profile", tags=["profile"])
MAX_BYTES = 2_000_000


def _upwork_connected(user: str) -> bool:
    try:
        from apps.api.auth.token_store import EncryptedTokenStore
        return EncryptedTokenStore().connected(user, "upwork")
    except Exception:  # noqa: BLE001 - no encryption key configured = not connected
        return False


async def _out(request: Request, user: str, p: dict) -> ProfileOut:
    return ProfileOut(**p, personas=personas(), upwork_connected=_upwork_connected(user), username=user)


@router.get("", response_model=ProfileOut)
async def get_my_profile(request: Request, user: str = User):
    return await _out(request, user, await get_profile(request.app.state.store, user))


@router.put("", response_model=ProfileOut)
async def update_my_profile(body: ProfileIn, request: Request, user: str = User):
    try:
        p = await save_profile(request.app.state.store, user, body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return await _out(request, user, p)


def _case_study(md: str, persona: str, filename: str) -> tuple[str, str]:
    """Give an uploaded Markdown case study front matter if it has none (id, title from the first heading)."""
    if md.lstrip().startswith("---"):
        return md, re.search(r'id:\s*"?([^"\n]+)', md).group(1) if re.search(r'id:\s*"?([^"\n]+)', md) else filename
    slug = re.sub(r"[^a-z0-9]+", "-", Path(filename).stem.lower()).strip("-")[:40] or "case"
    title = next((ln.lstrip("# ").strip() for ln in md.splitlines() if ln.strip()), slug)[:120]
    eid = f"{persona}-upload-{slug}"
    meta = {"id": eid, "title": title, "project": title, "skills": [], "date": "", "client_industry": "", "outcome": "delivered"}
    return "---\n" + "\n".join(f"{k}: {json.dumps(v)}" for k, v in meta.items()) + "\n---\n" + md, eid


@router.post("/portfolio", response_model=PortfolioUpload)
async def upload_portfolio(file: UploadFile, request: Request, user: str = User):
    """Add work to the user's portfolio: a PDF CV (split into sections) or a Markdown case study. The Portfolio server
    re-indexes on its next call, so the evidence is available to the agents immediately."""
    persona = (await get_profile(request.app.state.store, user))["persona"]
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "file too large (max 2 MB)")
    name = Path(file.filename or "upload").name
    base = PERSONAS_DIR / persona
    if name.lower().endswith(".pdf"):
        if not data.startswith(b"%PDF"):
            raise HTTPException(422, "not a PDF file")
        (base / "cv.pdf").write_bytes(data)
        from rag.ingest.cv_loader import cv_items
        items = cv_items(base / "cv.pdf", persona)
        return PortfolioUpload(persona=persona, kind="cv", evidence_ids=[i["evidence_id"] for i in items])
    if name.lower().endswith(".md"):
        md, eid = _case_study(data.decode("utf-8", errors="replace"), persona, name)
        (base / "case_studies").mkdir(parents=True, exist_ok=True)
        (base / "case_studies" / f"upload-{re.sub(r'[^a-z0-9]+', '-', Path(name).stem.lower())[:40]}.md").write_text(md, encoding="utf-8")
        return PortfolioUpload(persona=persona, kind="case_study", evidence_ids=[eid])
    raise HTTPException(422, "upload a PDF CV or a Markdown (.md) case study")
