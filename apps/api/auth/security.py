"""Minimal multi-user auth: users from env APP_USERS="demo:demo123,reviewer:...",
signed bearer tokens (HMAC-SHA256, 12h expiry). Passwords never logged."""
import base64
import hashlib
import hmac
import os
import time

from fastapi import Depends, HTTPException, Query, Request

TTL = 12 * 3600


def _secret() -> bytes:
    return os.getenv("APP_SECRET", "dev-secret-change-me").encode()


def users() -> dict[str, str]:
    raw = os.getenv("APP_USERS", "demo:demo123")
    return dict(p.split(":", 1) for p in raw.split(",") if ":" in p)


def check_password(username: str, password: str) -> bool:
    expected = users().get(username)
    return expected is not None and hmac.compare_digest(expected, password)


def make_token(username: str) -> str:
    body = f"{username}|{int(time.time()) + TTL}"
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{body}|{sig}".encode()).decode()


def read_token(token: str) -> str | None:
    try:
        username, exp, sig = base64.urlsafe_b64decode(token.encode()).decode().split("|")
    except Exception:  # noqa: BLE001
        return None
    good = hmac.new(_secret(), f"{username}|{exp}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(good, sig) or int(exp) < time.time():
        return None
    return username


def current_user(request: Request, token: str | None = Query(None, include_in_schema=False)) -> str:
    """Bearer header, or ?token= (EventSource cannot send headers)."""
    auth = request.headers.get("authorization", "")
    raw = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else token
    user = read_token(raw or "")
    if not user:
        raise HTTPException(401, "not signed in")
    return user


User = Depends(current_user)
