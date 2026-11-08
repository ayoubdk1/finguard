import uuid
from starlette.testclient import TestClient
from app.main import app

client = TestClient(app)


def _create_authenticated_user():
    app.dependency_overrides.clear()
    email = f"session-user-{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPassword!123"

    reg = client.post(
        "/auth/register",
        json={
            "email": email,
            "full_name": "Session Tester",
            "password": password,
        },
    )
    assert reg.status_code == 201

    login = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"User-Agent": "FinGuardMobile/1.0"},
    )
    assert login.status_code == 200
    token_data = login.json()
    return token_data


def test_list_active_sessions():
    auth = _create_authenticated_user()
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    resp = client.get("/auth/sessions", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_active"] >= 1
    assert any("FinGuardMobile" in (s.get("user_agent") or "") for s in data["sessions"])


def test_revoke_active_session_blocks_refresh():
    auth = _create_authenticated_user()
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    list_resp = client.get("/auth/sessions", headers=headers)
    assert list_resp.status_code == 200
    session_id = list_resp.json()["sessions"][0]["id"]

    del_resp = client.delete(f"/auth/sessions/{session_id}", headers=headers)
    assert del_resp.status_code == 204

    refresh_resp = client.post(
        "/auth/refresh",
        json={"refresh_token": auth["refresh_token"]},
    )
    assert refresh_resp.status_code == 401


def test_revoke_nonexistent_session_returns_404():
    auth = _create_authenticated_user()
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    random_id = uuid.uuid4()
    del_resp = client.delete(f"/auth/sessions/{random_id}", headers=headers)
    assert del_resp.status_code == 404
