"""Outbound webhooks: HMAC-SHA256 signed JSON, https only (unless explicitly allowed), private addresses blocked."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
from collections.abc import Callable
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from procureai.config.settings import get_settings
from procureai.infrastructure.database.models import Webhook
from procureai.shared.errors import ValidationAppError
from procureai.shared.types import utcnow

logger = logging.getLogger(__name__)
EVENTS = ("agent.task.completed", "agent.task.failed", "agent.task.awaiting_approval", "workflow.run.completed", "workflow.run.failed", "document.processed")
Sender = Callable[[str, bytes, dict[str, str]], int]


def validate_url(url: str) -> None:
    s = get_settings()
    u = urlparse(url)
    if u.scheme not in ("https", "http") or not u.hostname:
        raise ValidationAppError("Webhook URL must be an http(s) URL.")
    if s.allow_private_webhooks:
        return
    if u.scheme != "https":
        raise ValidationAppError("Webhook URL must use https.")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or 443, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise ValidationAppError("Webhook host could not be resolved.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValidationAppError("Webhook URL must not point to a private or local address.")


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _http_sender(url: str, body: bytes, headers: dict[str, str]) -> int:
    return httpx.post(url, content=body, headers=headers, timeout=4.0, follow_redirects=False).status_code


def dispatch(session: Session, org_id: str | None, event: str, payload: dict, sender: Sender | None = None) -> int:
    """Send ``event`` to every active matching webhook of the organization. Never raises; returns the delivered count."""
    if not org_id:
        return 0
    sender = sender or _http_sender
    delivered = 0
    for hook in session.scalars(select(Webhook).where(Webhook.org_id == org_id, Webhook.is_active.is_(True))):
        if hook.events and event not in hook.events:
            continue
        body = json.dumps({"event": event, "created_at": utcnow().isoformat(), "data": payload}, default=str).encode()
        headers = {"Content-Type": "application/json", "X-ProcuraMind-Event": event, "X-ProcuraMind-Signature": sign(hook.secret, body)}
        try:
            code = sender(hook.url, body, headers)
            hook.last_status = f"HTTP {code}"
            delivered += 1 if 200 <= code < 300 else 0
        except Exception as exc:  # boundary: remote endpoint failures must never break the platform
            hook.last_status = f"error: {type(exc).__name__}"
            logger.warning("Webhook delivery failed", extra={"webhook_id": hook.id})
    return delivered
