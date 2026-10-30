import os
from uuid import uuid4

from fastapi.testclient import TestClient

os.environ.setdefault(
    "FINGUARD_JWT_SECRET",
    "test-secret-key-at-least-32-chars-long-12345",
)

from app.main import app  # noqa: E402
from app.security.tokens import verify_access_token  # noqa: E402

client = TestClient(app)


def test_register_and_login_success():
    email = f"auth-{uuid4().hex[:8]}@example.com"
    password = "StrongPassword123!"

    reg = client.post(
        "/auth/register",
        json={
            "email": email,
            "full_name": "Alice Martin",
            "password": password,
        },
    )
    assert reg.status_code == 201, reg.text
    data = reg.json()
    assert data["email"] == email
    assert data["full_name"] == "Alice Martin"
    assert data["role"] == "CUSTOMER"
    assert "password" not in data
    assert "password_hash" not in data

    login = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )
    assert login.status_code == 200, login.text
    token_data = login.json()
    assert token_data["token_type"] == "bearer"
    user_id = verify_access_token(token_data["access_token"])
    assert str(user_id) == data["id"]


def test_register_duplicate_email_returns_409():
    email = f"dup-{uuid4().hex[:8]}@example.com"
    payload = {
        "email": email,
        "full_name": "Bob Dup",
        "password": "StrongPassword123!",
    }

    first = client.post("/auth/register", json=payload)
    assert first.status_code == 201, first.text

    second = client.post("/auth/register", json=payload)
    assert second.status_code == 409, second.text


def test_login_wrong_password_returns_401():
    email = f"wrong-{uuid4().hex[:8]}@example.com"
    client.post(
        "/auth/register",
        json={
            "email": email,
            "full_name": "Charlie Test",
            "password": "StrongPassword123!",
        },
    )

    res = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "WrongPassword999!",
        },
    )
    assert res.status_code == 401, res.text

