import uuid
from fastapi.testclient import TestClient
from app.main import app


def test_public_registration_is_disabled():
    client = TestClient(app)
    resp = client.post(
        "/auth/register",
        json={
            "email": f"pub.{uuid.uuid4().hex[:8]}@example.com",
            "full_name": "Public User",
            "password": "StrongPassword123!",
        },
    )
    assert resp.status_code == 403


def test_admin_user_lifecycle_and_login_history():
    client = TestClient(app)
    email = f"managed.{uuid.uuid4().hex[:8]}@example.com"
    initial_pw = "InitialPass123!"
    updated_pw = "UpdatedAdminPass456!"

    # 1. Admin creates user
    create_resp = client.post(
        "/admin/users",
        json={
            "email": email,
            "full_name": "Managed User",
            "password": initial_pw,
            "role": "FRAUD_ANALYST",
            "status": "ACTIVE",
        },
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "ACTIVE"
    assert create_resp.json()["role"] == "FRAUD_ANALYST"

    # 2. User logs in successfully
    login_ok = client.post(
        "/auth/login",
        json={"email": email, "password": initial_pw},
    )
    assert login_ok.status_code == 200
    assert "access_token" in login_ok.json()

    # 3. Admin checks active sessions (at least 1)
    sess_resp = client.get(f"/admin/users/{user_id}/sessions")
    assert sess_resp.status_code == 200
    assert sess_resp.json()["total_active"] >= 1

    # 4. Admin suspends user -> active sessions revoked & login blocked
    suspend_resp = client.patch(
        f"/admin/users/{user_id}",
        json={"status": "SUSPENDED", "full_name": "Managed User Updated"},
    )
    assert suspend_resp.status_code == 200
    assert suspend_resp.json()["status"] == "SUSPENDED"

    login_blocked = client.post(
        "/auth/login",
        json={"email": email, "password": initial_pw},
    )
    assert login_blocked.status_code == 403

    sess_after = client.get(f"/admin/users/{user_id}/sessions")
    assert sess_after.json()["total_active"] == 0

    # 5. Admin reactivates user and resets password
    reactivate = client.patch(
        f"/admin/users/{user_id}",
        json={"status": "ACTIVE"},
    )
    assert reactivate.status_code == 200

    reset_resp = client.post(
        f"/admin/users/{user_id}/reset-password",
        json={"new_password": updated_pw},
    )
    assert reset_resp.status_code == 200

    # 6. Login with new password works
    login_new = client.post(
        "/auth/login",
        json={"email": email, "password": updated_pw},
    )
    assert login_new.status_code == 200

    # 7. Admin checks login history (success + blocked + success)
    hist_resp = client.get(f"/admin/users/{user_id}/login-history")
    assert hist_resp.status_code == 200
    history = hist_resp.json()
    assert len(history) >= 3
    assert any(item["success"] is False for item in history)
    assert any(item["success"] is True for item in history)
