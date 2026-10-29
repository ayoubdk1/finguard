import pytest
from uuid import uuid4

from app.security.passwords import (
    hash_password,
    verify_password,
)

from app.security.tokens import (
    create_access_token,
    verify_access_token,
)


# TEST 1: Password hashing
def test_password_hashing():
    password = "SecurePassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$argon2")
    assert verify_password(password, hashed)


# TEST 2: Incorrect password
def test_wrong_password():
    hashed = hash_password("CorrectPassword123!")

    assert not verify_password(
        "WrongPassword123!",
        hashed
    )


# TEST 3: Empty password
def test_empty_password():
    with pytest.raises(ValueError):
        hash_password("")


# TEST 4: Valid JWT
def test_valid_access_token(monkeypatch):
    monkeypatch.setenv(
        "FINGUARD_JWT_SECRET",
        "test-secret-" + "a" * 64
    )

    user_id = uuid4()
    token = create_access_token(user_id)

    assert verify_access_token(token) == user_id


# TEST 5: Invalid JWT signature
def test_invalid_token_signature(monkeypatch):
    monkeypatch.setenv(
        "FINGUARD_JWT_SECRET",
        "test-secret-" + "a" * 64
    )

    token = create_access_token(uuid4())

    monkeypatch.setenv(
        "FINGUARD_JWT_SECRET",
        "different-secret-" + "b" * 64
    )

    with pytest.raises(ValueError):
        verify_access_token(token)


# TEST 6: Missing JWT secret
def test_missing_jwt_secret(monkeypatch):
    monkeypatch.delenv(
        "FINGUARD_JWT_SECRET",
        raising=False
    )

    with pytest.raises(RuntimeError):
        create_access_token(uuid4())