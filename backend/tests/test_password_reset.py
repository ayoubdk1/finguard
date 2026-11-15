import uuid
from fastapi.testclient import TestClient
from app.main import app


def test_forgot_and_reset_password_flow(monkeypatch):
    monkeypatch.setenv('FINGUARD_EXPOSE_RESET_TOKEN', '1')
    client = TestClient(app)

    email = f"reset.{uuid.uuid4().hex[:8]}@example.com"
    old_password = "OldSecurePassword123!"
    new_password = "NewSecure#Pass2026!"

    # 1. Register user
    reg = client.post(
        "/admin/users",
        json={"email": email, "full_name": "Reset User", "password": old_password},
    )
    assert reg.status_code == 201

    # 2. Request password reset token via EmailSender
    captured = []
    class _Cap:
        def send_password_reset(self, to_email, tok):
            captured.append(tok)
    import app.routers.auth as auth_mod
    orig = auth_mod.get_email_sender
    auth_mod.get_email_sender = lambda: _Cap()
    try:
        forgot = client.post("/auth/forgot-password", json={"email": email})
        assert forgot.status_code == 200
        assert "reset_token" not in forgot.json()
        reset_token = captured[0]
    finally:
        auth_mod.get_email_sender = orig

    # 3. Reset password with token
    reset = client.post(
        "/auth/reset-password",
        json={"reset_token": reset_token, "new_password": new_password},
    )
    assert reset.status_code == 200
    assert reset.json()["status"] == "password_reset_success"

    # 4. Token cannot be reused a second time
    reuse = client.post(
        "/auth/reset-password",
        json={"reset_token": reset_token, "new_password": "AnotherPassword789!"},
    )
    assert reuse.status_code == 400

    # 5. Old password no longer works, new password works
    old_login = client.post(
        "/auth/login",
        json={"email": email, "password": old_password},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/auth/login",
        json={"email": email, "password": new_password},
    )
    assert new_login.status_code == 200
    assert "access_token" in new_login.json()
