import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, Transaction
from app.security.rate_limit import extract_client_ip

EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]{1,2})[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
IPV4_RE = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}\b")
GENESIS_HASH = "0" * 64


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


def get_client_ip(request: Request) -> str | None:
    ip = extract_client_ip(request)
    return None if ip == "unknown" else ip[:45]


def get_request_id(request: Request | None) -> str | None:
    if request is None:
        return None
    rid = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")
    return str(rid) if rid else None


def compute_audit_hash(
    *,
    prev_hash: str,
    actor_id: UUID | None,
    actor_role: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    details: dict[str, Any] | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    ip_address: str | None,
    request_id: str | None,
) -> str:
    payload = {
        "prev_hash": prev_hash,
        "actor_id": str(actor_id) if actor_id is not None else None,
        "actor_role": actor_role,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": details,
        "before": before,
        "after": after,
        "ip_address": ip_address,
        "request_id": request_id,
    }
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record_audit_event(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | UUID | None = None,
    actor_id: UUID | None = None,
    actor_role: str | None = None,
    ip_address: str | None = None,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    clean_details = dict(details) if details else None
    if clean_details and isinstance(clean_details.get("email"), str):
        clean_details["email"] = mask_email(clean_details["email"])
    masked_ip = mask_ip(ip_address)
    res_id_str = str(resource_id) if resource_id is not None else None

    latest_hash = db.scalar(
        select(AuditLog.hash)
        .where(AuditLog.hash.is_not(None))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(1)
    )
    prev_hash = latest_hash or GENESIS_HASH
    entry_hash = compute_audit_hash(
        prev_hash=prev_hash,
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=res_id_str,
        details=clean_details,
        before=before,
        after=after,
        ip_address=masked_ip,
        request_id=request_id,
    )
    entry = AuditLog(
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=res_id_str,
        details=clean_details,
        before=before,
        after=after,
        ip_address=masked_ip,
        request_id=request_id,
        prev_hash=prev_hash,
        hash=entry_hash,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.flush()
    return entry


def verify_audit_log_chain(db: Session) -> list[dict[str, Any]]:
    """Verify SHA-256 hash chain integrity across all hashed audit_log rows."""
    rows = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.hash.is_not(None))
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        ).all()
    )
    errors: list[dict[str, Any]] = []
    expected_prev = GENESIS_HASH
    for row in rows:
        if row.prev_hash != expected_prev:
            errors.append(
                {
                    "id": str(row.id),
                    "error": "prev_hash_mismatch",
                    "expected": expected_prev,
                    "actual": row.prev_hash,
                }
            )
        recomputed = compute_audit_hash(
            prev_hash=row.prev_hash or GENESIS_HASH,
            actor_id=row.actor_id,
            actor_role=row.actor_role,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            details=row.details,
            before=row.before,
            after=row.after,
            ip_address=row.ip_address,
            request_id=row.request_id,
        )
        if row.hash != recomputed:
            errors.append(
                {
                    "id": str(row.id),
                    "error": "hash_mismatch",
                    "expected": recomputed,
                    "actual": row.hash,
                }
            )
        expected_prev = row.hash or expected_prev
    return errors


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
