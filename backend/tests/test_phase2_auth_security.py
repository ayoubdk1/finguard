from datetime import datetime, timedelta, timezone
import uuid
import jwt
import pyotp
import pytest
from cryptography.fernet import Fernet

from app.db.models import User
from app.main import app, validate_production_config
from app.security.dependencies import get_current_user
from app.security.mfa import decrypt_mfa_secret, encrypt_mfa_secret
from app.security.passwords import hash_password, validate_password_policy
from app.security.rate_limit import reset_login_rate_limits
from app.security.tokens import JWT_ALGORITHM, JWT_AUDIENCE, JWT_ISSUER, create_access_token, get_jwt_secret


def _login(client, email: str, password: str, headers=None):
    return client.post("/auth/login", json={"email": email, "password": password}, headers=headers or {})


def test_mfa_setup_disable_stepup_replay_lockout_and_backup_codes(client, session):
    reset_login_rate_limits()
    pwd = "StrongPassword#2026!"
    user = User(id=uuid.uuid4(), email=f"mfa-{uuid.uuid4().hex[:8]}@example.com", full_name="MFA User", password_hash=hash_password(pwd), role="CUSTOMER", status="ACTIVE")
    session.add(user)
    session.commit()

    prev = app.dependency_overrides.pop(get_current_user, None)
    try:
        tok = _login(client, user.email, pwd).json()["access_token"]
        hdrs = {"Authorization": f"Bearer {tok}"}

        stale_payload = {"sub": str(user.id), "type": "access", "iat": datetime.now(timezone.utc) - timedelta(minutes=20), "exp": datetime.now(timezone.utc) + timedelta(minutes=10), "iss": JWT_ISSUER, "aud": JWT_AUDIENCE, "jti": str(uuid.uuid4())}
        stale_tok = jwt.encode(stale_payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)
        assert client.post("/auth/mfa/setup", headers={"Authorization": f"Bearer {stale_tok}"}, json={"current_password": pwd}).status_code == 403

        setup = client.post("/auth/mfa/setup", headers=hdrs, json={"current_password": pwd})
        assert setup.status_code == 200
        secret = setup.json()["secret"]
        code1 = pyotp.TOTP(secret).now()

        en = client.post("/auth/mfa/enable", headers=hdrs, json={"code": code1})
        assert en.status_code == 200
        backup_codes = en.json()["backup_codes"]
        assert len(backup_codes) == 10

        assert client.post("/auth/mfa/setup", headers=hdrs, json={"current_password": pwd}).status_code == 400

        mfa_tok1 = _login(client, user.email, pwd).json()["mfa_token"]
        assert client.post("/auth/mfa/login", json={"mfa_token": mfa_tok1, "code": code1}).status_code == 401

        assert client.post("/auth/mfa/login", json={"mfa_token": mfa_tok1, "code": backup_codes[0]}).status_code == 200
        assert client.post("/auth/mfa/login", json={"mfa_token": mfa_tok1, "code": backup_codes[1]}).status_code == 401

        regen = client.post("/auth/mfa/backup-codes/regenerate", headers=hdrs)
        assert regen.status_code == 200
        assert len(regen.json()["backup_codes"]) == 10

        reset_login_rate_limits()
        mfa_tok2 = _login(client, user.email, pwd).json()["mfa_token"]
        for _ in range(5):
            assert client.post("/auth/mfa/login", json={"mfa_token": mfa_tok2, "code": "000000"}).status_code == 401
        reset_login_rate_limits()
        assert client.post("/auth/mfa/login", json={"mfa_token": mfa_tok2, "code": backup_codes[2]}).status_code == 423

        db_u = session.get(User, user.id)
        db_u.mfa_locked_until = None
        db_u.mfa_failed_attempts = 0
        db_u.mfa_last_totp_step = None
        session.commit()
        code2 = pyotp.TOTP(secret).now()
        assert client.post("/auth/mfa/disable", headers=hdrs, json={"password": "wrong", "code": code2}).status_code == 401
        assert client.post("/auth/mfa/disable", headers=hdrs, json={"password": pwd, "code": code2}).status_code == 200
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev


def test_rate_limit_xff_buckets_and_retry_after(client):
    reset_login_rate_limits()
    for i in range(5):
        assert _login(client, f"u{i}@example.com", "wrong", headers={"X-Forwarded-For": "10.0.0.1"}).status_code == 401
    r_blocked = _login(client, "u9@example.com", "wrong", headers={"X-Forwarded-For": "10.0.0.1"})
    assert r_blocked.status_code == 429
    assert "Retry-After" in r_blocked.headers
    assert _login(client, "u9@example.com", "wrong", headers={"X-Forwarded-For": "10.0.0.2"}).status_code == 401


def test_suspended_user_rejected_immediately(client, session):
    user = User(id=uuid.uuid4(), email=f"susp-{uuid.uuid4().hex[:8]}@example.com", full_name="Susp", password_hash=hash_password("StrongPassword#2026!"), role="CUSTOMER", status="ACTIVE")
    session.add(user)
    session.commit()
    prev = app.dependency_overrides.pop(get_current_user, None)
    try:
        tok = create_access_token(user.id)
        r_me = client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}); assert r_me.status_code == 200, r_me.text
        user.status = "SUSPENDED"
        session.commit()
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 403
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev


def test_fernet_mfa_rotation_and_password_policy(monkeypatch):
    k1, k2 = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setenv("FINGUARD_MFA_ENCRYPTION_KEY", k1)
    monkeypatch.setenv("FINGUARD_MFA_ENCRYPTION_KEY_ID", "k1")
    enc = encrypt_mfa_secret("JBSWY3DPEHPK3PXP")
    assert enc.startswith("enc:v2:k1:")
    monkeypatch.setenv("FINGUARD_MFA_ENCRYPTION_KEY", k2)
    monkeypatch.setenv("FINGUARD_MFA_ENCRYPTION_KEY_ID", "k2")
    monkeypatch.setenv("FINGUARD_MFA_PREVIOUS_KEYS", f"k1:{k1}")
    assert decrypt_mfa_secret(enc) == "JBSWY3DPEHPK3PXP"
    with pytest.raises(ValueError):
        validate_password_policy("Password123!")
    validate_password_policy("FinGuard#Unique2026!")


def test_forgot_password_never_exposes_token(client):
    reset_login_rate_limits()
    r = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert r.status_code == 200
    assert "reset_token" not in r.json()


def test_fail_closed_production_config(monkeypatch):
    monkeypatch.setenv("FINGUARD_ENV", "production")
    monkeypatch.setenv("FINGUARD_JWT_SECRET", "short")
    with pytest.raises(RuntimeError):
        validate_production_config()
    monkeypatch.setenv("FINGUARD_JWT_SECRET", "a" * 32)
    monkeypatch.setenv("FINGUARD_DEMO_MODE", "1")
    with pytest.raises(RuntimeError):
        validate_production_config()
    monkeypatch.delenv("FINGUARD_DEMO_MODE", raising=False)
    monkeypatch.setenv("FINGUARD_CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError):
        validate_production_config()


def test_authorization_matrix_and_request_id(client):
    r_ok = client.get("/health", headers={"X-Request-ID": "req-123_abc"})
    assert r_ok.headers["X-Request-ID"] == "req-123_abc"
    r_bad = client.get("/health", headers={"X-Request-ID": "bad id!@#$%"})
    assert r_bad.headers["X-Request-ID"] != "bad id!@#$%"

    prev = app.dependency_overrides.get(get_current_user)
    try:
        for role, expected in [("CUSTOMER", 403), ("AUDITOR", 403), ("FRAUD_ANALYST", 200), ("ADMIN", 200)]:
            app.dependency_overrides[get_current_user] = lambda r=role: User(id=uuid.uuid4(), email="r@example.com", full_name="R", role=r, status="ACTIVE")
            resp = client.post("/risk/assess", json={"amount_cents": 1000, "transfers_last_10min": 0, "account_age_minutes": 100, "failed_transfers_last_hour": 0})
            assert resp.status_code == expected
    finally:
        if prev is not None:
            app.dependency_overrides[get_current_user] = prev
