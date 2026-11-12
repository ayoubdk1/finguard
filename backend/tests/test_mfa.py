import uuid
import pyotp
from starlette.testclient import TestClient
from app.main import app

client = TestClient(app)


def _create_authenticated_user():
    email = f"mfa-user-{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPassword!123"

    reg = client.post(
        "/admin/users",
        json={
            "email": email,
            "full_name": "MFA Tester",
            "password": password,
        },
    )
    assert reg.status_code == 201
    app.dependency_overrides.clear()

    login = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    token_data = login.json()
    return email, password, token_data["access_token"]


def test_mfa_setup_and_enable_flow():
    email, password, access_token = _create_authenticated_user()
    headers = {"Authorization": f"Bearer {access_token}"}

    # 1. Setup MFA
    setup_resp = client.post("/auth/mfa/setup", headers=headers)
    assert setup_resp.status_code == 200
    setup_data = setup_resp.json()
    secret = setup_data["secret"]
    assert "otpauth://" in setup_data["otpauth_uri"]

    # 2. Reject invalid code
    bad_resp = client.post("/auth/mfa/enable", headers=headers, json={"code": "000000"})
    assert bad_resp.status_code == 400

    # 3. Enable with valid code
    valid_code = pyotp.TOTP(secret).now()
    ok_resp = client.post("/auth/mfa/enable", headers=headers, json={"code": valid_code})
    assert ok_resp.status_code == 200

    # 4. Login now requires MFA
    mfa_login_resp = client.post("/auth/login", json={"email": email, "password": password})
    assert mfa_login_resp.status_code == 200
    mfa_data = mfa_login_resp.json()
    assert mfa_data["mfa_required"] is True
    assert mfa_data["mfa_token"] is not None
    assert not mfa_data["access_token"]

    # 5. Complete login with MFA challenge
    totp_now = pyotp.TOTP(secret).now()
    final_login = client.post(
        "/auth/mfa/login",
        json={"mfa_token": mfa_data["mfa_token"], "code": totp_now},
    )
    assert final_login.status_code == 200
    final_data = final_login.json()
    assert final_data["access_token"]
    assert final_data["refresh_token"]

    # 6. Disable MFA
    disable_code = pyotp.TOTP(secret).now()
    disable_resp = client.post(
        "/auth/mfa/disable",
        headers={"Authorization": f"Bearer {final_data['access_token']}"},
        json={"code": disable_code},
    )
    assert disable_resp.status_code == 200

    # 7. Login no longer requires MFA
    normal_login = client.post("/auth/login", json={"email": email, "password": password})
    assert normal_login.status_code == 200
    assert normal_login.json()["mfa_required"] is False
    assert normal_login.json()["access_token"]
