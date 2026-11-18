import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, Transaction

EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]{1,2})[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
IPV4_RE = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}\b")


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    prefix = local[:2] if len(local) >= 2 else local[:1]
    return f"{prefix}***@{domain}"


def mask_ip(ip: str | None) -> str | None:
    if not ip:
        return ip
    if "." in ip:
        parts = ip.split(".")
        if len(parts) == 4:
            return ".".join(parts[:3]) + ".***"
    if ":" in ip:
        parts = ip.split(":")
        return ":".join(parts[:3]) + ":****"
    return "***"


def mask_pii_in_text(text: str) -> str:
    text = EMAIL_RE.sub(r"\1***\2", text)
    return IPV4_RE.sub(r"\1.***", text)


def get_client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def get_request_id(request: Request | None) -> str | None:
    if request is None:
        return None
    rid = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")
    return str(rid) if rid else None


def record_audit_event(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | UUID | None = None,
    actor_id: UUID | None = None,
    ip_address: str | None = None,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    clean_details = dict(details) if details else None
    if clean_details and isinstance(clean_details.get("email"), str):
        clean_details["email"] = mask_email(clean_details["email"])
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        details=clean_details,
        ip_address=mask_ip(ip_address),
        request_id=request_id,
    )
    db.add(entry)
    return entry


def cleanup_expired_idempotency_keys(db: Session, now: datetime | None = None) -> int:
    cutoff = now or datetime.now(timezone.utc)
    rows = db.scalars(
        select(Transaction).where(
            Transaction.idempotency_expires_at.is_not(None),
            Transaction.idempotency_expires_at < cutoff,
            ~Transaction.idempotency_scope.like("expired:%"),
        )
    ).all()
    for tx in rows:
        tx.idempotency_scope = f"expired:{tx.id}"
    if rows:
        db.commit()
    return len(rows)
