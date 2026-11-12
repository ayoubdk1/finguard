import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.security.tokens import create_mfa_token, verify_access_token
from app.security.mfa import encrypt_mfa_secret, decrypt_mfa_secret, generate_mfa_secret


def test_mfa_pending_token_rejected_as_access_token():
    user_id = uuid.uuid4()
    mfa_tok = create_mfa_token(user_id)
    with pytest.raises(ValueError):
        verify_access_token(mfa_tok)


def test_post_users_requires_admin_permission():
    app.dependency_overrides.clear()
    client = TestClient(app)
    resp = client.post(
        "/users",
        json={"email": f"unauth.{uuid.uuid4().hex[:8]}@example.com", "full_name": "Anon"},
    )
    assert resp.status_code == 401


def test_forgot_password_does_not_leak_reset_token_by_default(monkeypatch):
    monkeypatch.delenv("FINGUARD_EXPOSE_RESET_TOKEN", raising=False)
    client = TestClient(app)
    email = f"noleak.{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/admin/users",
        json={"email": email, "full_name": "No Leak", "password": "SecurePassword123!"},
    )
    resp = client.post("/auth/forgot-password", json={"email": email})
    assert resp.status_code == 200
    assert resp.json()["reset_token"] is None


def test_mfa_secret_encrypted_at_rest():
    raw = generate_mfa_secret()
    enc = encrypt_mfa_secret(raw)
    assert enc.startswith("enc:v1:")
    assert raw not in enc
    assert decrypt_mfa_secret(enc) == raw


def test_csp_and_hsts_headers_present():
    client = TestClient(app)
    res = client.get("/health")
    assert "max-age=" in res.headers.get("Strict-Transport-Security", "")
    assert "default-src 'self'" in res.headers.get("Content-Security-Policy", "")
