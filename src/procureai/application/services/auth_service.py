from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from procureai.application.services.audit import record_audit
from procureai.config.settings import get_settings
from procureai.infrastructure.database.models import User
from procureai.infrastructure.security import create_access_token, hash_password, verify_password
from procureai.shared.enums import Role
from procureai.shared.errors import AuthenticationError, ConflictError, PermissionDeniedError

_DUMMY_HASH = hash_password("not-a-real-password")


def register_user(session: Session, email: str, full_name: str, password: str) -> User:
    settings = get_settings()
    email = email.strip().lower()
    first_user = session.scalar(select(func.count()).select_from(User)) == 0
    if not settings.allow_registration and not first_user:
        raise PermissionDeniedError("Registration is disabled. Ask an administrator for an account.")
    if session.scalar(select(User).where(User.email == email)):
        raise ConflictError("An account with this email already exists.")
    user = User(
        email=email,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        role=Role.ADMIN.value if first_user else Role.OFFICER.value,
    )
    session.add(user)
    session.flush()
    from procureai.application.services.org_service import create_personal_org

    create_personal_org(session, user)
    record_audit(session, actor_id=user.id, action="user.registered", resource_type="user", resource_id=user.id)
    session.commit()
    return user


def authenticate(session: Session, email: str, password: str) -> tuple[User, str, int]:
    user = session.scalar(select(User).where(User.email == email.strip().lower()))
    ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)  # constant-time-ish
    if not user or not ok or not user.is_active:
        raise AuthenticationError("Incorrect email or password.")
    token, expires = create_access_token(user.id, user.role)
    record_audit(session, actor_id=user.id, action="user.login", resource_type="user", resource_id=user.id)
    session.commit()
    return user, token, expires
