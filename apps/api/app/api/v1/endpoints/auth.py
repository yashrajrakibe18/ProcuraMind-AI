from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import DB, CurrentUser
from app.core.ratelimit import login_limiter
from procureai.application.dto.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from procureai.application.services import auth_service
from procureai.shared.errors import AuthenticationError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: RegisterIn, db: DB) -> UserOut:
    return UserOut.model_validate(auth_service.register_user(db, data.email, data.full_name, data.password))


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, request: Request, db: DB) -> TokenOut:
    key = f"{request.client.host if request.client else '-'}:{data.email.lower()}"
    login_limiter.check(key)
    try:
        user, token, expires = auth_service.authenticate(db, data.email, data.password)
    except AuthenticationError:
        login_limiter.hit(key)
        raise
    login_limiter.reset(key)
    return TokenOut(access_token=token, expires_in=expires, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
