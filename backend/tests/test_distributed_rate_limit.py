from starlette.testclient import TestClient
from app.main import app
from app.security.rate_limit import LOGIN_MAX_ATTEMPTS, reset_login_rate_limits

client = TestClient(app)


def test_redis_distributed_rate_limit_blocks_after_max_attempts():
    reset_login_rate_limits()
    for _ in range(LOGIN_MAX_ATTEMPTS):
        resp = client.post(
            "/auth/login",
            json={"email": "nobody@example.com", "password": "WrongPassword!123"},
        )
        assert resp.status_code == 401

    blocked = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "WrongPassword!123"},
    )
    assert blocked.status_code == 429
    assert "too many login attempts" in blocked.json()["detail"].lower()


def test_rate_limit_graceful_fallback_when_redis_unavailable(monkeypatch):
    reset_login_rate_limits()
    monkeypatch.setenv("FINGUARD_REDIS_URL", "redis://127.0.0.1:6399/0")

    for _ in range(LOGIN_MAX_ATTEMPTS):
        resp = client.post(
            "/auth/login",
            json={"email": "nobody@example.com", "password": "WrongPassword!123"},
        )
        assert resp.status_code == 401

    blocked = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "WrongPassword!123"},
    )
    assert blocked.status_code == 429
