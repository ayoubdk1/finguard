import os
from uuid import uuid4

import pytest
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



@pytest.fixture
def real_auth():
    """Disable the conftest auth override so real token checks run."""
    saved = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.update(saved)


def test_auth_me_requires_valid_token(real_auth):
    # 1. Missing token -> 401
    unauth = client.get("/auth/me")
    assert unauth.status_code == 401, unauth.text

    # 2. Invalid token -> 401
    bad = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid.token.value"},
    )
    assert bad.status_code == 401, bad.text

    # 3. Valid token -> 200 with user profile
    email = f"me-{uuid4().hex[:8]}@example.com"
    password = "StrongPassword123!"
    reg = client.post(
        "/auth/register",
        json={
            "email": email,
            "full_name": "Diana Prince",
            "password": password,
        },
    )
    assert reg.status_code == 201

    login = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    token = login.json()["access_token"]

    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200, me.text
    assert me.json()["email"] == email
    assert me.json()["full_name"] == "Diana Prince"


from fastapi import HTTPException  # noqa: E402
import pytest  # noqa: E402
from app.db.models import Account, AccountType, User  # noqa: E402
from app.security.dependencies import verify_account_ownership  # noqa: E402


def test_verify_account_ownership_blocks_other_customer():
    owner_id = uuid4()
    other_id = uuid4()
    account = Account(
        id=uuid4(),
        user_id=owner_id,
        name="Checking",
        account_type=AccountType.CUSTOMER,
        currency="USD",
    )
    owner = User(id=owner_id, email="a@b.com", full_name="Owner", role="CUSTOMER")
    intruder = User(id=other_id, email="c@d.com", full_name="Intruder", role="CUSTOMER")
    admin = User(id=other_id, email="admin@b.com", full_name="Admin", role="ADMIN")

    # Owner and ADMIN succeed
    verify_account_ownership(account, owner)
    verify_account_ownership(account, admin)

    # Another customer gets 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        verify_account_ownership(account, intruder)
    assert exc_info.value.status_code == 403


def test_protected_routes_require_token_and_enforce_ownership():
    saved_overrides = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    try:
        # 1. Calling protected routes without a token -> 401
        assert client.get(f"/accounts/{uuid4()}/balance").status_code == 401
        assert client.get(f"/accounts/{uuid4()}/transactions").status_code == 401
        assert client.get("/monitoring/events").status_code == 401

        # 2. Register User A and User B
        email_a = f"usera-{uuid4().hex[:8]}@example.com"
        email_b = f"userb-{uuid4().hex[:8]}@example.com"
        password = "StrongPassword123!"

        reg_a = client.post(
            "/auth/register",
            json={"email": email_a, "full_name": "User A", "password": password},
        )
        user_a_id = reg_a.json()["id"]
        token_a = client.post(
            "/auth/login", json={"email": email_a, "password": password}
        ).json()["access_token"]

        client.post(
            "/auth/register",
            json={"email": email_b, "full_name": "User B", "password": password},
        )
        token_b = client.post(
            "/auth/login", json={"email": email_b, "password": password}
        ).json()["access_token"]

        # 3. User B cannot create an account for User A -> 403
        forbid_acc = client.post(
            "/accounts",
            json={"user_id": user_a_id, "name": "Spoof", "currency": "USD"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert forbid_acc.status_code == 403, forbid_acc.text

        # 4. User A creates their own account -> 201
        own_acc = client.post(
            "/accounts",
            json={"user_id": user_a_id, "name": "Checking", "currency": "USD"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert own_acc.status_code == 201, own_acc.text
        account_a_id = own_acc.json()["id"]

        # 5. User B cannot view User A's balance or transactions -> 403
        forbid_bal = client.get(
            f"/accounts/{account_a_id}/balance",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert forbid_bal.status_code == 403

        # 6. User A can view their own balance -> 200
        ok_bal = client.get(
            f"/accounts/{account_a_id}/balance",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert ok_bal.status_code == 200
    finally:
        app.dependency_overrides.update(saved_overrides)
