import uuid
from fastapi.testclient import TestClient
from app.main import app


def test_forgot_and_reset_password_flow():
    client = TestClient(app)

    email = f"reset.{uuid.uuid4().hex[:8]}@example.com"
    old_password = "OldSecurePassword123!"
    new_password = "NewSecurePassword456!"

    # 1. Register user
    reg = client.post(
        "/auth/register",
        json={"email": email, "full_name": "Reset User", "password": old_password},
    )
    assert reg.status_code == 201

    # 2. Request password reset token
    forgot = client.post("/auth/forgot-password", json={"email": email})
    assert forgot.status_code == 200
    data = forgot.json()
    assert data["reset_token"] is not None
    reset_token = data["reset_token"]

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
