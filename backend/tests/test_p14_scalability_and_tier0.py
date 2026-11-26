import uuid
from pathlib import Path

from app.db.models import AccountBalance, FraudAlert, FraudAlertStatus, User
from app.main import app
from app.security.dependencies import get_current_user
from app.security.passwords import hash_password
from app.security.rate_limit import record_failed_login_and_check_spray, reset_login_rate_limits
from app.services.ledger import EntryInput, get_balance, post_transaction, verify_balance_projections
from app.services.risk_assessment import assess_transaction_risk


def test_p14_account_balance_projection_stays_in_sync_with_ledger(session, world):
    src = world["alice"]
    dst = world["bob"]
    funding = world["funding"]

    post_transaction(
        session=session,
        idempotency_key=str(uuid.uuid4()),
        idempotency_scope="p14:seed",
        request_hash=uuid.uuid4().hex,
        entries=[EntryInput(funding.id, -50_000), EntryInput(src.id, 50_000)],
        description="seed",
    )
    post_transaction(
        session=session,
        idempotency_key=str(uuid.uuid4()),
        idempotency_scope="p14:xfer",
        request_hash=uuid.uuid4().hex,
        entries=[EntryInput(src.id, -12_500), EntryInput(dst.id, 12_500)],
        description="transfer",
    )

    src_proj = session.get(AccountBalance, src.id)
    dst_proj = session.get(AccountBalance, dst.id)
    assert src_proj is not None and src_proj.balance == 37_500 == get_balance(session, src.id)
    assert dst_proj is not None and dst_proj.balance == 12_500 == get_balance(session, dst.id)
    # SYSTEM_FUNDING must NOT have a customer balance projection row
    assert session.get(AccountBalance, funding.id) is None
    assert verify_balance_projections(session) == []


def test_p14_cursor_pagination_transactions_fraud_and_users(client, session, world):
    src = world["alice"]
    dst = world["bob"]
    funding = world["funding"]
    u = session.get(User, src.user_id)

    post_transaction(
        session=session,
        idempotency_key=str(uuid.uuid4()),
        idempotency_scope="p14:seed2",
        request_hash=uuid.uuid4().hex,
        entries=[EntryInput(funding.id, -100_000), EntryInput(src.id, 100_000)],
        description="seed2",
    )
    for i in range(4):
        post_transaction(
            session=session,
            idempotency_key=str(uuid.uuid4()),
            idempotency_scope=f"p14:tx:{i}",
            request_hash=uuid.uuid4().hex,
            entries=[EntryInput(src.id, -1000), EntryInput(dst.id, 1000)],
            description=f"tx {i}",
        )

    prev = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: u
    try:
        p1 = client.get(f"/accounts/{src.id}/transactions?limit=2")
        assert p1.status_code == 200
        d1 = p1.json()
        assert len(d1["transactions"]) == 2
        assert d1["next_cursor"] is not None

        p2 = client.get(f"/accounts/{src.id}/transactions?limit=2&cursor={d1['next_cursor']}")
        assert p2.status_code == 200
        d2 = p2.json()
        assert len(d2["transactions"]) == 2
        ids1 = {t["transaction_id"] for t in d1["transactions"]}
        ids2 = {t["transaction_id"] for t in d2["transactions"]}
        assert ids1.isdisjoint(ids2)
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev

    # Fraud alerts cursor pagination
    for _ in range(3):
        session.add(FraudAlert(transaction_id=None, account_id=src.id, risk_score=800, reasons=["TEST"], status=FraudAlertStatus.PENDING.value))
    session.commit()
    fa1 = client.get("/fraud/alerts?limit=2")
    assert fa1.status_code == 200
    assert len(fa1.json()) == 2
    assert "X-Next-Cursor" in fa1.headers
    fa2 = client.get(f"/fraud/alerts?limit=2&cursor={fa1.headers['X-Next-Cursor']}")
    assert fa2.status_code == 200
    assert len(fa2.json()) >= 1



def test_p14_cursor_pagination_admin_users(client, session):
    for i in range(3):
        session.add(User(email=f"cur-{i}-{uuid.uuid4().hex[:6]}@example.com", full_name="Cur", password_hash=hash_password("StrongPassword#2026!"), role="CUSTOMER", status="ACTIVE"))
    session.commit()
    au1 = client.get("/admin/users?limit=2")
    assert au1.status_code == 200
    assert len(au1.json()) == 2
    assert "X-Next-Cursor" in au1.headers
    au2 = client.get(f"/admin/users?limit=2&cursor={au1.headers['X-Next-Cursor']}")
    assert au2.status_code == 200
    assert len(au2.json()) >= 1


def test_p14_risk_score_always_0_to_100_scale():
    res = assess_transaction_risk(
        amount_cents=1000,
        transfers_last_10min=0,
        account_age_minutes=10_000,
        failed_transfers_last_hour=0,
        is_new_destination=True,
        amount_vs_avg_ratio=4.0,
    )
    assert res["risk_score"] == 35.0
    assert res["decision"] == "REVIEW"


def test_p14_tier0_nginx_compose_and_progressive_delay():
    root = Path(__file__).resolve().parents[2]
    nginx = (root / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in nginx
    assert "$proxy_add_x_forwarded_for" not in nginx

    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    assert "8001:8000" not in compose

    reset_login_rate_limits()
    d1 = record_failed_login_and_check_spray("victim@example.com", "203.0.113.10")
    d2 = record_failed_login_and_check_spray("victim@example.com", "203.0.113.10")
    d3 = record_failed_login_and_check_spray("victim@example.com", "203.0.113.10")
    assert d1 == 0.0
    assert d2 == 0.25
    assert d3 == 0.5
