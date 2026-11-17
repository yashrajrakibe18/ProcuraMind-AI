from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from procureai.config.logging import request_id_var
from procureai.infrastructure.database.models import AuditEvent


def record_audit(
    session: Session,
    *,
    actor_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    project_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Stage an audit event in the caller's transaction. Metadata must be safe (no secrets/document text)."""
    rid = request_id_var.get()
    session.add(
        AuditEvent(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            project_id=project_id,
            request_id=None if rid == "-" else rid,
            event_metadata=metadata or {},
        )
    )
