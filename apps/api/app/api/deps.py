from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from procureai.application.context import AppContext, get_context
from procureai.infrastructure.database.models import User
from procureai.infrastructure.database.session import get_session_factory
from procureai.infrastructure.security import decode_access_token
from procureai.shared.errors import AuthenticationError

bearer = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


DB = Annotated[Session, Depends(get_db)]


def app_context() -> AppContext:
    return get_context()


Ctx = Annotated[AppContext, Depends(app_context)]


def current_user(db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> User:
    if creds is None:
        raise AuthenticationError("Authentication required.")
    payload = decode_access_token(creds.credentials)
    user = db.get(User, payload.get("sub", ""))
    if user is None or not user.is_active:
        raise AuthenticationError("Account not found or disabled.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
