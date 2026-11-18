import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError

from app.db.models import AuditLog, Transaction, User
from app.main import app
from app.security.dependencies import get_current_user
from app.services.audit import cleanup_expired_idempotency_keys, mask_email, mask_ip, record_audit_event

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.reconcile_ledger import run_reconciliation_with_metrics  # noqa: E402


def test_p4_audit_log_append_only_and_masking(session):
    assert mask_email("ayoub@example.com") == "ay***@example.com"
    assert mask_ip("192.168.1.42") == "192.168.1.***"

    entry = record_audit_event(
        session,
        action="LOGIN_FAILURE",
        resource_type="AUTH",
        ip_address="192.168.1.42",
        request_id="req-p4-1",
        details={"email": "ayoub@example.com"},
    )
    session.commit()
    assert entry.ip_address == "192.168.1.***"
    assert entry.details["email"] == "ay***@example.com"

    with pytest.raises(DBAPIError):
        session.execute(update(AuditLog).where(AuditLog.id == entry.id).values(action="TAMPERED"))
        session.flush()
    session.rollback()

    with pytest.raises(DBAPIError):
        session.execute(delete(AuditLog).where(AuditLog.id == entry.id))
        session.flush()
    session.rollback()


def test_p4_admin_controls_self_last_admin_and_four_eyes(client, session):
    admin1 = User(id=uuid.uuid4(), email=f"a1-{uuid.uuid4().hex[:6]}@example.com", full_name="A1", password_hash="x", role="ADMIN", status="ACTIVE")
    admin2 = User(id=uuid.uuid4(), email=f"a2-{uuid.uuid4().hex[:6]}@example.com", full_name="A2", password_hash="x", role="ADMIN", status="ACTIVE")
    target = User(id=uuid.uuid4(), email=f"u1-{uuid.uuid4().hex[:6]}@example.com", full_name="U1", password_hash="x", role="CUSTOMER", status="ACTIVE")
    session.add_all([admin1, admin2, target])
    session.commit()

    prev = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: admin1
    try:
        assert client.patch(f"/admin/users/{admin1.id}", json={"role": "CUSTOMER"}).status_code == 409
        assert client.patch(f"/admin/users/{admin1.id}", json={"status": "DISABLED"}).status_code == 409

        r_req = client.post(f"/admin/approvals/role-change?user_id={target.id}&new_role=FRAUD_ANALYST")
        assert r_req.status_code == 201
        approval_id = r_req.json()["id"]

        assert client.post(f"/admin/approvals/{approval_id}/approve").status_code == 409

        app.dependency_overrides[get_current_user] = lambda: admin2
        assert client.post(f"/admin/approvals/{approval_id}/approve").status_code == 200
        session.expire_all()
        assert session.get(User, target.id).role == "FRAUD_ANALYST"
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev


def test_p4_idempotency_retention_and_reconciliation_gauge(client, session, world):
    r = client.post("/deposits", headers={"Idempotency-Key": f"p4-idem-{uuid.uuid4()}"}, json={"account_id": str(world["alice"].id), "amount_cents": 10_000})
    assert r.status_code == 201
    tx = session.scalars(select(Transaction).order_by(Transaction.created_at.desc())).first()
    assert tx.idempotency_expires_at is not None
    tx.idempotency_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    session.commit()

    cleaned = cleanup_expired_idempotency_keys(session)
    assert cleaned >= 1

    res = run_reconciliation_with_metrics(session)
    assert res["status"] == "reconciled"
    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    assert "finguard_ledger_reconciliation_imbalance 0.0" in metrics_resp.text


def test_p4_account_statement_derived_balance_check(client, world):
    assert client.post("/deposits", headers={"Idempotency-Key": f"p4s1-{uuid.uuid4()}"}, json={"account_id": str(world["alice"].id), "amount_cents": 50_000}).status_code == 201
    assert client.post("/transfers", headers={"Idempotency-Key": f"p4s2-{uuid.uuid4()}"}, json={"source_account_id": str(world["alice"].id), "destination_account_id": str(world["bob"].id), "amount_cents": 15_000}).status_code == 201

    st = client.get(f"/accounts/{world['alice'].id}/statement")
    assert st.status_code == 200
    data = st.json()
    assert data["derived_balance_check"] is True
    assert data["closing_balance_cents"] == 35_000
    assert len(data["entries"]) >= 2
