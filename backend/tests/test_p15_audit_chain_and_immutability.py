import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.models import AuditLog, FraudAlert, FraudAlertStatus, User
from app.main import app
from app.security.dependencies import get_current_user
from app.security.passwords import hash_password
from app.services.audit import record_audit_event, verify_audit_log_chain
from app.services.ledger import EntryInput, post_transaction


def test_p15_audit_hash_chain_links_and_verifies(session):
    e1 = record_audit_event(session, action="TEST_EVT_1", resource_type="USER", resource_id="u1", actor_role="ADMIN", before={"a": 1}, after={"a": 2})
    e2 = record_audit_event(session, action="TEST_EVT_2", resource_type="USER", resource_id="u2", actor_role="AUDITOR", after={"b": 3})
    session.commit()

    assert e1.hash is not None and len(e1.hash) == 64
    assert e2.prev_hash == e1.hash
    assert e2.hash is not None and len(e2.hash) == 64
    assert verify_audit_log_chain(session) == []


def test_p15_transactions_immutable_status_and_description_trigger(session, world):
    tx = post_transaction(
        session=session,
        idempotency_key=str(uuid.uuid4()),
        idempotency_scope="p15:immut",
        request_hash=uuid.uuid4().hex,
        entries=[EntryInput(world["funding"].id, -5000), EntryInput(world["alice"].id, 5000)],
        description="original desc",
    )

    with pytest.raises(DBAPIError, match="immutable"):
        session.execute(text("UPDATE transactions SET description = 'tampered' WHERE id = :tid"), {"tid": tx.id})
    session.rollback()

    with pytest.raises(DBAPIError, match="immutable"):
        session.execute(text("UPDATE transactions SET status = 'FAILED' WHERE id = :tid"), {"tid": tx.id})
    session.rollback()


def test_p15_auditor_only_get_audit_and_route_instrumentation(client, session, world):
    auditor = User(id=uuid.uuid4(), email=f"aud-{uuid.uuid4().hex[:6]}@example.com", full_name="Aud", password_hash=hash_password("StrongPassword#2026!"), role="AUDITOR", status="ACTIVE")
    admin = User(id=uuid.uuid4(), email=f"adm-{uuid.uuid4().hex[:6]}@example.com", full_name="Adm", password_hash=hash_password("StrongPassword#2026!"), role="ADMIN", status="ACTIVE")
    session.add_all([auditor, admin])
    alert = FraudAlert(transaction_id=None, account_id=world["alice"].id, risk_score=850, reasons=["TEST"], status=FraudAlertStatus.PENDING.value)
    session.add(alert)
    session.commit()

    prev = app.dependency_overrides.get(get_current_user)
    try:
        # Admin creates deposit, updates account status, resolves fraud alert
        app.dependency_overrides[get_current_user] = lambda: admin
        r_dep = client.post("/deposits", headers={"Idempotency-Key": str(uuid.uuid4())}, json={"account_id": str(world["alice"].id), "amount_cents": 2500, "description": "dep"})
        assert r_dep.status_code == 201
        r_st = client.patch(f"/accounts/{world['bob'].id}/status", json={"status": "FROZEN"})
        assert r_st.status_code == 200
        r_fr = client.post(f"/fraud/alerts/{alert.id}/resolve", json={"decision": "APPROVED", "analyst_notes": "verified ok"})
        assert r_fr.status_code == 200

        # Non-auditor (even ADMIN) blocked on GET /audit
        assert client.get("/audit").status_code == 403

        # AUDITOR can read paginated audit log with hashes and before/after
        app.dependency_overrides[get_current_user] = lambda: auditor
        p1 = client.get("/audit?limit=2")
        assert p1.status_code == 200
        d1 = p1.json()
        assert len(d1["items"]) == 2
        assert d1["next_cursor"] is not None
        assert all(item["hash"] and item["prev_hash"] for item in d1["items"])

        p2 = client.get(f"/audit?limit=2&cursor={d1['next_cursor']}")
        assert p2.status_code == 200
        actions = {x["action"] for x in d1["items"] + p2.json()["items"]}
        assert {"DEPOSIT_CREATED", "ACCOUNT_STATUS_FROZEN", "FRAUD_ALERT_RESOLVED"}.issubset(actions)
        assert verify_audit_log_chain(session) == []
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev
