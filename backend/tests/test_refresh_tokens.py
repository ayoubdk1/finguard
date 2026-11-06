import uuid


def _register_and_login(client, monkeypatch):
    monkeypatch.setenv(
        "FINGUARD_JWT_SECRET",
        "super-secret-jwt-key-with-at-least-32-bytes!",
    )
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPassword!123"

    reg = client.post(
        "/auth/register",
        json={
            "email": email,
            "full_name": "Refresh Tester",
            "password": password,
        },
    )
    assert reg.status_code == 201

    login = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    data = login.json()
    assert data.get("access_token")
    assert data.get("refresh_token")
    return data


def test_refresh_token_rotation_issues_new_pair(client, monkeypatch):
    tokens = _register_and_login(client, monkeypatch)

    refreshed = client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()
    assert new_tokens["access_token"]
    assert new_tokens["refresh_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]


def test_refresh_token_reuse_detection_revokes_family(client, monkeypatch):
    tokens = _register_and_login(client, monkeypatch)
    first_refresh = tokens["refresh_token"]

    rotated = client.post(
        "/auth/refresh",
        json={"refresh_token": first_refresh},
    )
    assert rotated.status_code == 200
    second_refresh = rotated.json()["refresh_token"]

    replay = client.post(
        "/auth/refresh",
        json={"refresh_token": first_refresh},
    )
    assert replay.status_code == 401
    assert "reuse detected" in replay.json()["detail"].lower()

    after_compromise = client.post(
        "/auth/refresh",
        json={"refresh_token": second_refresh},
    )
    assert after_compromise.status_code == 401


def test_logout_revokes_refresh_token(client, monkeypatch):
    tokens = _register_and_login(client, monkeypatch)

    logout_resp = client.post(
        "/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert logout_resp.status_code == 204

    refresh_after_logout = client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_after_logout.status_code == 401
