import concurrent.futures
import time
import uuid
from decimal import Decimal
from unittest.mock import patch

import pyotp
from fastapi.testclient import TestClient

from app.db.models import AuditLog, ExchangeRate, MfaTokenState, RefreshToken, TransferAttempt, User
from app.db.session import SessionLocal
from app.main import app
from app.security.dependencies import get_current_user
from app.security.mfa import generate_backup_codes, hash_backup_code
from app.security.passwords import hash_password
from app.security.rate_limit import reset_login_rate_limits
from app.security.tokens import create_access_token
from app.services.ledger import EntryInput, post_transaction


def test_p13_refresh_token_race_allows_only_one_and_revokes_family():
    reset_login_rate_limits()
    pwd = "StrongPassword#2026!"
    uid = uuid.uuid4()
    email = f"race-{uuid.uuid4().hex[:8]}@example.com"
    with SessionLocal() as db:
        db.add(User(id=uid, email=email, full_name="Race User", password_hash=hash_password(pwd), role="CUSTOMER", status="ACTIVE"))
        db.commit()

    prev = app.dependency_overrides.pop(get_current_user, None)
    try:
        with TestClient(app) as tc:
            login = tc.post("/auth/login", json={"email": email, "password": pwd})
            assert login.status_code == 200
            refresh_tok = login.json()["refresh_token"]

            def do_refresh():
                return tc.post("/auth/refresh", json={"refresh_token": refresh_tok}).status_code

            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                statuses = list(pool.map(lambda _: do_refresh(), range(6)))

        assert statuses.count(200) == 1
        assert all(s == 401 for s in statuses if s != 200)
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev
        with SessionLocal() as db:
            db.query(RefreshToken).filter(RefreshToken.user_id == uid).delete()
            db.query(User).filter(User.id == uid).delete()
            db.commit()


def test_p13_refresh_does_not_renew_auth_time_and_mfa_setup_requires_password(client, session):
    reset_login_rate_limits()
    pwd = "StrongPassword#2026!"
    user = User(
        id=uuid.uuid4(),
        email=f"mfa-sec-{uuid.uuid4().hex[:8]}@example.com",
        full_name="MFA Sec",
        password_hash=hash_password(pwd),
        role="CUSTOMER",
        status="ACTIVE",
    )
    session.add(user)
    session.commit()

    prev = app.dependency_overrides.pop(get_current_user, None)
    try:
        login = client.post("/auth/login", json={"email": user.email, "password": pwd})
        assert login.status_code == 200
        tok = login.json()["access_token"]
        rt = login.json()["refresh_token"]

        bad = client.post("/auth/mfa/setup", headers={"Authorization": f"Bearer {tok}"}, json={"current_password": "WrongPassword#2026!"})
        assert bad.status_code == 401

        ref = client.post("/auth/refresh", json={"refresh_token": rt})
        assert ref.status_code == 200

        codes = generate_backup_codes(2)
        assert all(len(c.replace("-", "")) == 16 for c in codes)
        assert hash_backup_code(codes[0]).startswith("$argon2")
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev


def test_p13_parallel_mfa_login_no_500():
    reset_login_rate_limits()
    pwd = "StrongPassword#2026!"
    uid = uuid.uuid4()
    email = f"mfa-race-{uuid.uuid4().hex[:8]}@example.com"
    with SessionLocal() as db:
        db.add(User(id=uid, email=email, full_name="MFA Race", password_hash=hash_password(pwd), role="CUSTOMER", status="ACTIVE"))
        db.commit()

    prev = app.dependency_overrides.pop(get_current_user, None)
    try:
        with TestClient(app) as tc:
            tok = tc.post("/auth/login", json={"email": email, "password": pwd}).json()["access_token"]
            hdrs = {"Authorization": f"Bearer {tok}"}
            secret = tc.post("/auth/mfa/setup", headers=hdrs, json={"current_password": pwd}).json()["secret"]
            code = pyotp.TOTP(secret).at(int(time.time()) - 30)
            assert tc.post("/auth/mfa/enable", headers=hdrs, json={"code": code}).status_code == 200

            mfa_tok = tc.post("/auth/login", json={"email": email, "password": pwd}).json()["mfa_token"]
            totp_now = pyotp.TOTP(secret).now()

            def do_mfa():
                return tc.post("/auth/mfa/login", json={"mfa_token": mfa_tok, "code": totp_now}).status_code

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                statuses = list(pool.map(lambda _: do_mfa(), range(4)))

        assert 500 not in statuses
        assert statuses.count(200) <= 1
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev
        with SessionLocal() as db:
            db.query(MfaTokenState).filter(MfaTokenState.user_id == uid).delete()
            db.query(RefreshToken).filter(RefreshToken.user_id == uid).delete()
            db.query(User).filter(User.id == uid).delete()
            db.commit()


def test_p13_login_constant_time_calls_verify_for_unknown_email(client):
    reset_login_rate_limits()
    with patch("app.routers.auth.verify_password", return_value=False) as mock_verify:
        resp = client.post("/auth/login", json={"email": f"unknown-{uuid.uuid4().hex[:8]}@example.com", "password": "SomePassword#2026!"})
        assert resp.status_code == 401
        assert mock_verify.call_count == 1


def test_p13_admin_password_policy_and_governance(client, session):
    admin1 = User(id=uuid.uuid4(), email=f"adm1-{uuid.uuid4().hex[:6]}@example.com", full_name="Admin 1", password_hash=hash_password("StrongPassword#2026!"), role="ADMIN", status="ACTIVE")
    admin2 = User(id=uuid.uuid4(), email=f"adm2-{uuid.uuid4().hex[:6]}@example.com", full_name="Admin 2", password_hash=hash_password("StrongPassword#2026!"), role="ADMIN", status="ACTIVE")
    session.add_all([admin1, admin2])
    session.commit()

    prev = app.dependency_overrides.pop(get_current_user, None)
    try:
        hdr1 = {"Authorization": f"Bearer {create_access_token(admin1.id)}"}
        hdr2 = {"Authorization": f"Bearer {create_access_token(admin2.id)}"}

        weak = client.post("/admin/users", headers=hdr1, json={"email": f"wk-{uuid.uuid4().hex[:6]}@example.com", "full_name": "Weak", "password": "aaaaaaaaaaaa", "role": "CUSTOMER"})
        assert weak.status_code == 422

        strong_email = f"ok-{uuid.uuid4().hex[:6]}@example.com"
        created = client.post("/admin/users", headers=hdr1, json={"email": strong_email, "full_name": "Strong", "password": "StrongPassword#2026!", "role": "CUSTOMER"})
        assert created.status_code == 201
        uid = created.json()["id"]

        weak_reset = client.post(f"/admin/users/{uid}/reset-password", headers=hdr1, json={"new_password": "aaaaaaaaaaaa"})
        assert weak_reset.status_code == 422

        direct_prom = client.patch(f"/admin/users/{uid}", headers=hdr1, json={"role": "ADMIN"})
        assert direct_prom.status_code == 409

        assert client.post(f"/admin/approvals/role-change?user_id={uid}&new_role=SUPERUSER", headers=hdr1).status_code == 422

        req_resp = client.post(f"/admin/approvals/role-change?user_id={uid}&new_role=ADMIN", headers=hdr1)
        assert req_resp.status_code == 201
        app_id = req_resp.json()["id"]
        assert any(a["id"] == app_id for a in client.get("/admin/approvals?status_filter=PENDING", headers=hdr1).json())
        assert client.post(f"/admin/approvals/{app_id}/reject", headers=hdr2).status_code == 200

        logs = session.query(AuditLog).filter(AuditLog.action == "USER_CREATED", AuditLog.resource_id == uid).all()
        assert len(logs) == 1
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev


def test_p13_fraud_signals_wired_and_limit_failures_recorded(client, session, world):
    src = world["alice"]
    dst = world["bob"]
    u = session.get(User, src.user_id)
    post_transaction(
        session=session,
        idempotency_key=str(uuid.uuid4()),
        idempotency_scope="test:seed",
        request_hash=uuid.uuid4().hex,
        entries=[EntryInput(world["funding"].id, -50_000), EntryInput(src.id, 50_000)],
        description="seed alice",
    )

    if src.currency != "USD":
        session.add(ExchangeRate(base_currency=src.currency, target_currency="USD", rate=Decimal("1000000"), fee_bps=0))
        session.commit()

    captured = {}
    def fake_assess(**kwargs):
        captured.update(kwargs)
        return {"rules_risk_score": 10, "rules_decision": "ALLOW", "reason_codes": [], "review_recommended": False}

    prev = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: u
    try:
        client.post(
            "/transfers",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json={"source_account_id": str(src.id), "destination_account_id": str(dst.id), "amount_cents": 999_999_999, "description": "too big"},
        )
        attempts = session.query(TransferAttempt).filter(TransferAttempt.source_account_id == src.id, TransferAttempt.reason == "LIMIT_EXCEEDED").count()
        assert attempts >= 1

        with patch("app.routers.transfers.assess_transaction_risk", side_effect=fake_assess):
            r = client.post(
                "/transfers",
                headers={"Idempotency-Key": str(uuid.uuid4())},
                json={"source_account_id": str(src.id), "destination_account_id": str(dst.id), "amount_cents": 1000, "description": "wired signals"},
            )
            assert r.status_code == 201
        assert "is_new_destination" in captured
        assert "amount_vs_avg_ratio" in captured
        assert "normalized_amount_usd_cents" in captured
        assert captured["failed_transfers_last_hour"] >= 1
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev


def test_p14_fx_replay_returns_conversion_details(client, session, world):
    from app.db.models import Account, AccountType
    src = world["alice"]
    u = session.get(User, src.user_id)
    eur_user_acct = Account(user_id=u.id, name="Alice EUR", account_type=AccountType.CUSTOMER, currency="EUR")
    sys_usd = Account(name="SYSTEM_FX", account_type=AccountType.SYSTEM, currency="USD")
    sys_eur = Account(name="SYSTEM_FX", account_type=AccountType.SYSTEM, currency="EUR")
    session.add_all([eur_user_acct, sys_usd, sys_eur])
    session.add(ExchangeRate(base_currency="USD", target_currency="EUR", rate=Decimal("900000"), fee_bps=50))
    session.commit()

    post_transaction(
        session=session,
        idempotency_key=str(uuid.uuid4()),
        idempotency_scope="test:fxseed",
        request_hash=uuid.uuid4().hex,
        entries=[EntryInput(world["funding"].id, -20_000), EntryInput(src.id, 20_000)],
        description="seed fx",
    )

    prev = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: u
    try:
        idem = str(uuid.uuid4())
        payload = {"source_account_id": str(src.id), "destination_account_id": str(eur_user_acct.id), "amount_cents": 10_000, "description": "fx replay"}
        r1 = client.post("/transfers", headers={"Idempotency-Key": idem}, json=payload)
        assert r1.status_code == 201
        r2 = client.post("/transfers", headers={"Idempotency-Key": idem}, json=payload)
        assert r2.status_code == 201
        d2 = r2.json()
        assert d2["is_fx"] is True
        assert d2["converted_amount_cents"] == r1.json()["converted_amount_cents"]
        assert d2["fee_cents"] == r1.json()["fee_cents"]
        assert d2["exchange_rate"] == r1.json()["exchange_rate"]
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev


def test_p15_smtp_sender_uses_starttls():
    from unittest.mock import MagicMock
    from app.services.email import SMTPEmailSender

    mock_smtp = MagicMock()
    mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
    mock_smtp.__exit__ = MagicMock(return_value=False)

    with patch("app.services.email.smtplib.SMTP", return_value=mock_smtp):
        sender = SMTPEmailSender(host="smtp.example.com", port=587, sender="noreply@example.com", username="u", password="p", use_tls=True)
        sender.send_password_reset("user@example.com", "tok-123")

    assert mock_smtp.starttls.call_count == 1
    assert mock_smtp.login.call_count == 1
    assert mock_smtp.send_message.call_count == 1


def test_p16_cache_control_no_store_and_ops_auth(client, monkeypatch):
    r_health = client.get("/health")
    assert r_health.headers.get("Cache-Control") == "no-store"

    monkeypatch.setenv("FINGUARD_METRICS_TOKEN", "ops-secret-token")
    assert client.get("/metrics").status_code == 401
    assert client.get("/health/ready").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer ops-secret-token"}).status_code == 200
