from __future__ import annotations

import uuid
from datetime import UTC, datetime


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
