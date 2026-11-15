from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import select
from starlette.testclient import TestClient

from app import main as api_module
from app.db.models import Account, AccountType, ExchangeRate, Transaction, User
from app.main import app
from app.security.dependencies import get_current_user


def _set_user(monkeypatch, user: User):
    app.dependency_overrides[get_current_user] = lambda: user


def test_1_1_fx_concurrent_opposite_directions_no_deadlock_or_500(monkeypatch):
    from app.db import session as db_session_module
    from app.routers import transfers as r_transfers
    prev_override = app.dependency_overrides.get(get_current_user)
    monkeypatch.setattr(r_transfers, "SessionLocal", db_session_module.SessionLocal)

    try:
        with db_session_module.SessionLocal() as db:
            u1 = User(id=uuid.uuid4(), email=f"fxu1-{uuid.uuid4()}@finguard.local", full_name="FX U1", password_hash="x", role="ADMIN", status="ACTIVE")
            u2 = User(id=uuid.uuid4(), email=f"fxu2-{uuid.uuid4()}@finguard.local", full_name="FX U2", password_hash="x", role="ADMIN", status="ACTIVE")
            db.add_all([u1, u2])
            db.flush()

            a_usd = Account(id=uuid.uuid4(), user_id=u1.id, name="A USD", account_type=AccountType.CUSTOMER, currency="USD")
            b_eur = Account(id=uuid.uuid4(), user_id=u1.id, name="B EUR", account_type=AccountType.CUSTOMER, currency="EUR")
            c_eur = Account(id=uuid.uuid4(), user_id=u2.id, name="C EUR", account_type=AccountType.CUSTOMER, currency="EUR")
            d_usd = Account(id=uuid.uuid4(), user_id=u2.id, name="D USD", account_type=AccountType.CUSTOMER, currency="USD")
            db.add_all([a_usd, b_eur, c_eur, d_usd])

            for cname in ("USD", "EUR"):
                if db.scalar(select(Account).where(Account.name == "SYSTEM_FX", Account.currency == cname)) is None:
                    db.add(Account(id=uuid.uuid4(), name="SYSTEM_FX", account_type=AccountType.SYSTEM, currency=cname))
            if db.scalar(select(Account).where(Account.name == "SYSTEM_FUNDING", Account.currency == "USD")) is None:
                db.add(Account(id=uuid.uuid4(), name="SYSTEM_FUNDING", account_type=AccountType.SYSTEM, currency="USD"))
            db.commit()

        app.dependency_overrides[get_current_user] = lambda: u1
        c0 = TestClient(app)
        assert c0.post("/deposits", headers={"Idempotency-Key": f"d1-{uuid.uuid4()}"}, json={"account_id": str(a_usd.id), "amount_cents": 1_000_000}).status_code == 201
        assert c0.post("/transfers", headers={"Idempotency-Key": f"d2-{uuid.uuid4()}"}, json={"source_account_id": str(a_usd.id), "destination_account_id": str(c_eur.id), "amount_cents": 500_000, "description": "seed eur"}).status_code == 201

        def _run_fx(idx: int):
            c = TestClient(app)
            if idx % 2 == 0:
                payload = {"source_account_id": str(a_usd.id), "destination_account_id": str(b_eur.id), "amount_cents": 1000, "description": f"fx-{idx}"}
            else:
                payload = {"source_account_id": str(c_eur.id), "destination_account_id": str(d_usd.id), "amount_cents": 1000, "description": f"fx-{idx}"}
            return c.post("/transfers", headers={"Idempotency-Key": f"fx-thread-{idx}-{uuid.uuid4()}"}, json=payload).status_code

        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(_run_fx, range(8)))
        assert all(s in (201, 409) for s in statuses), f"Unexpected statuses: {statuses}"
    finally:
        if prev_override is not None:
            app.dependency_overrides[get_current_user] = prev_override
        else:
            app.dependency_overrides.pop(get_current_user, None)
        from sqlalchemy import delete
        from app.db.models import LedgerEntry, OutboxEvent
        with db_session_module.SessionLocal() as clean_db:
            tx_ids = list(clean_db.scalars(select(LedgerEntry.transaction_id).where(LedgerEntry.account_id.in_([a_usd.id, b_eur.id, c_eur.id, d_usd.id]))).all())
            if tx_ids:
                clean_db.execute(delete(OutboxEvent).where(OutboxEvent.aggregate_id.in_(tx_ids)))
                clean_db.commit()

def test_1_2_customer_cannot_self_mint_deposit_admin_can(client, session, world):
    cust = User(id=uuid.uuid4(), email="cust-dep@finguard.local", full_name="Cust", password_hash="x", role="CUSTOMER", status="ACTIVE")
    session.add(cust)
    session.flush()
    acct = Account(user_id=cust.id, name="Cust USD", account_type=AccountType.CUSTOMER, currency="USD")
    session.add(acct)
    session.commit()

    # Customer gets 403
    prev_override = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: cust
    try:
        r_cust = client.post("/deposits", headers={"Idempotency-Key": f"cdep-{uuid.uuid4()}"}, json={"account_id": str(acct.id), "amount_cents": 10000})
        assert r_cust.status_code == 403
    finally:
        if prev_override is not None:
            app.dependency_overrides[get_current_user] = prev_override
        else:
            app.dependency_overrides.pop(get_current_user, None)

    # Admin succeeds (201)
    r_adm = client.post("/deposits", headers={"Idempotency-Key": f"adep-{uuid.uuid4()}"}, json={"account_id": str(acct.id), "amount_cents": 10000})
    assert r_adm.status_code == 201


def test_1_3_refund_authorization_window_and_no_refund_of_refund(client, session, world):
    payer = User(id=uuid.uuid4(), email=f"payer-{uuid.uuid4()}@finguard.local", full_name="Payer", password_hash="x", role="CUSTOMER", status="ACTIVE")
    recipient = User(id=uuid.uuid4(), email=f"recip-{uuid.uuid4()}@finguard.local", full_name="Recipient", password_hash="x", role="CUSTOMER", status="ACTIVE")
    session.add_all([payer, recipient])
    session.flush()
    payer_acct = Account(id=uuid.uuid4(), user_id=payer.id, name="Payer USD", account_type=AccountType.CUSTOMER, currency="USD")
    recip_acct = Account(id=uuid.uuid4(), user_id=recipient.id, name="Recip USD", account_type=AccountType.CUSTOMER, currency="USD")
    session.add_all([payer_acct, recip_acct])
    session.commit()

    assert client.post("/deposits", headers={"Idempotency-Key": f"rdep-{uuid.uuid4()}"}, json={"account_id": str(payer_acct.id), "amount_cents": 50000}).status_code == 201

    prev = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: payer
    try:
        tr = client.post("/transfers", headers={"Idempotency-Key": f"rtr-{uuid.uuid4()}"}, json={"source_account_id": str(payer_acct.id), "destination_account_id": str(recip_acct.id), "amount_cents": 10000, "description": "Pay Bob"})
        assert tr.status_code == 201
        tx_id = tr.json()["transaction_id"]

        # Payer is rejected (403)
        r_payer = client.post(f"/transfers/{tx_id}/refund", headers={"Idempotency-Key": f"ref-{uuid.uuid4()}"})
        assert r_payer.status_code == 403

        # Recipient is accepted (201)
        app.dependency_overrides[get_current_user] = lambda: recipient
        r_rec = client.post(f"/transfers/{tx_id}/refund", headers={"Idempotency-Key": f"ref-{uuid.uuid4()}"})
        assert r_rec.status_code == 201
        refund_tx_id = r_rec.json()["transaction_id"]
        # Second refund returns 409
        assert client.post(f"/transfers/{tx_id}/refund", headers={"Idempotency-Key": f"ref-{uuid.uuid4()}"}).status_code == 409
        # Refunding a refund returns 409
        assert client.post(f"/transfers/{refund_tx_id}/refund", headers={"Idempotency-Key": f"ref2-{uuid.uuid4()}"}).status_code == 409

        # Expired (>30 days) transfer cannot be refunded
        app.dependency_overrides[get_current_user] = lambda: payer
        tr_old = client.post("/transfers", headers={"Idempotency-Key": f"oldtr-{uuid.uuid4()}"}, json={"source_account_id": str(payer_acct.id), "destination_account_id": str(recip_acct.id), "amount_cents": 1000, "description": "Old"})
        assert tr_old.status_code == 201
        old_tx = session.get(Transaction, uuid.UUID(tr_old.json()["transaction_id"]))
        old_tx.created_at = datetime.now(timezone.utc) - timedelta(days=31)
        session.commit()
        app.dependency_overrides[get_current_user] = lambda: recipient
        assert client.post(f"/transfers/{old_tx.id}/refund", headers={"Idempotency-Key": f"refold-{uuid.uuid4()}"}).status_code == 422
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev
        else:
            app.dependency_overrides.pop(get_current_user, None)



def test_1_4_replay_before_limits_succeeds_when_daily_limit_full(client, world):
    # Fund Alice with $60,000
    assert client.post("/deposits", headers={"Idempotency-Key": f"ldep-{uuid.uuid4()}"}, json={"account_id": str(world["alice"].id), "amount_cents": 6_000_000}).status_code == 201

    replay_key = f"replay-key-{uuid.uuid4()}"
    first = client.post(
        "/transfers",
        headers={"Idempotency-Key": replay_key},
        json={"source_account_id": str(world["alice"].id), "destination_account_id": str(world["bob"].id), "amount_cents": 1_000_000, "description": "First"},
    )
    assert first.status_code == 201
    first_body = first.json()

    # Fill remaining daily limit ($40,000 more)
    for i in range(4):
        r = client.post(
            "/transfers",
            headers={"Idempotency-Key": f"fill-{i}-{uuid.uuid4()}"},
            json={"source_account_id": str(world["alice"].id), "destination_account_id": str(world["bob"].id), "amount_cents": 1_000_000, "description": f"Fill {i}"},
        )
        assert r.status_code == 201

    # New key is rejected by daily limit (422)
    blocked = client.post(
        "/transfers",
        headers={"Idempotency-Key": f"over-{uuid.uuid4()}"},
        json={"source_account_id": str(world["alice"].id), "destination_account_id": str(world["bob"].id), "amount_cents": 100_000, "description": "Over"},
    )
    assert blocked.status_code == 422

    # Replay earlier key STILL returns 201 with original transaction_id
    replayed = client.post(
        "/transfers",
        headers={"Idempotency-Key": replay_key},
        json={"source_account_id": str(world["alice"].id), "destination_account_id": str(world["bob"].id), "amount_cents": 1_000_000, "description": "First"},
    )
    assert replayed.status_code == 201
    assert replayed.json()["transaction_id"] == first_body["transaction_id"]
