import uuid
from sqlalchemy import select
from starlette.requests import Request
from app.main import app
from app.security.dependencies import get_current_user
from app.db.models import Account, AccountType, FraudAlert, TransferAttempt, User
from app.security.passwords import hash_password
from app.security.rate_limit import extract_client_ip
from app.services.ledger import get_balance


def _req(peer: str, xff: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "client": (peer, 12345), "headers": headers})


def test_xff_spoofing_protection():
    assert extract_client_ip(_req("203.0.113.5", "1.2.3.4")) == "203.0.113.5"
    assert extract_client_ip(_req("127.0.0.1", "9.9.9.9, 198.51.100.7")) == "198.51.100.7"


def test_logout_revokes_access_token_immediately(client, session):
    email = f"rev-{uuid.uuid4().hex[:8]}@example.com"
    pwd = "StrongPassword!123"
    u = User(id=uuid.uuid4(), email=email, full_name="Rev User", password_hash=hash_password(pwd), role="CUSTOMER", status="ACTIVE")
    session.add(u)
    session.commit()
    prev = app.dependency_overrides.pop(get_current_user, None)
    try:
        tok = client.post("/auth/login", json={"email": email, "password": pwd}).json()
        headers = {"Authorization": f"Bearer {tok['access_token']}"}
        assert client.get("/auth/me", headers=headers).status_code == 200
        assert client.post("/auth/logout", headers=headers, json={"refresh_token": tok["refresh_token"]}).status_code == 204
        assert client.get("/auth/me", headers=headers).status_code == 401
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev


def test_fx_fee_booked_and_replay_preserves_amounts(client, session, world):
    bob_eur = Account(user_id=world["bob"].user_id, name="Bob EUR", account_type=AccountType.CUSTOMER, currency="EUR")
    session.add(bob_eur)
    session.commit()
    assert client.post("/deposits", headers={"Idempotency-Key": f"d-{uuid.uuid4()}"}, json={"account_id": str(world["alice"].id), "amount_cents": 50_000}).status_code == 201
    key = f"fx-{uuid.uuid4()}"
    payload = {"source_account_id": str(world["alice"].id), "destination_account_id": str(bob_eur.id), "amount_cents": 10_000, "description": "FX test"}
    first = client.post("/transfers", headers={"Idempotency-Key": key}, json=payload)
    assert first.status_code == 201, first.text
    replay = client.post("/transfers", headers={"Idempotency-Key": key}, json=payload)
    assert replay.status_code == 201, replay.text
    assert replay.json()["converted_amount_cents"] == first.json()["converted_amount_cents"]
    assert replay.json()["fee_cents"] == first.json()["fee_cents"] == 50
    fee_acct = session.scalar(select(Account).where(Account.name == "SYSTEM_FX_FEE_REVENUE", Account.currency == "USD"))
    assert fee_acct is not None and get_balance(session, fee_acct.id) >= 50


def test_simulated_hold_blocks_transfer_pre_commit(client, session, world, monkeypatch):
    assert client.post("/deposits", headers={"Idempotency-Key": f"hd-{uuid.uuid4()}"}, json={"account_id": str(world["alice"].id), "amount_cents": 50_000}).status_code == 201
    before_bob = get_balance(session, world["bob"].id)
    monkeypatch.setattr("app.routers.transfers.assess_transaction_risk", lambda **kw: {"rules_risk_score": 95, "rules_decision": "SIMULATED_HOLD", "reason_codes": ["LARGE_AMOUNT"], "ml_probability": 0.95, "review_recommended": True})
    resp = client.post("/transfers", headers={"Idempotency-Key": f"hold-{uuid.uuid4()}"}, json={"source_account_id": str(world["alice"].id), "destination_account_id": str(world["bob"].id), "amount_cents": 25_000})
    assert resp.status_code == 403
    assert get_balance(session, world["bob"].id) == before_bob
    att = session.scalar(select(TransferAttempt).where(TransferAttempt.source_account_id == world["alice"].id).order_by(TransferAttempt.created_at.desc()))
    assert att is not None and att.reason == "FRAUD_HOLD"
    alert = session.scalar(select(FraudAlert).where(FraudAlert.account_id == world["alice"].id).order_by(FraudAlert.created_at.desc()))
    assert alert is not None and alert.status == "PENDING"
