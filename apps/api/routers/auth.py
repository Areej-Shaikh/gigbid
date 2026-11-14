from fastapi import APIRouter, HTTPException

from apps.api.auth.security import check_password, make_token
from apps.api.schemas.models import LoginIn, LoginOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn):
    if not check_password(body.username, body.password):
        raise HTTPException(401, "wrong username or password")
    return LoginOut(token=make_token(body.username), username=body.username)
