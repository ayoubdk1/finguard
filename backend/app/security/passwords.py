import re

from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()

BREACHED_PASSWORDS = frozenset({
    "123456789012",
    "password123!",
    "password1234",
    "admin123456!",
    "qwerty12345!",
    "welcome1234!",
    "changeme123!",
    "finguard123!",
    "letmein1234!",
    "p@ssword1234",
})


def validate_password_policy(password: str) -> None:
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters long")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"[0-9]", password):
        raise ValueError("Password must contain at least one digit")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("Password must contain at least one special character")
    if password.strip().lower() in BREACHED_PASSWORDS:
        raise ValueError("Password appears in a known breached-password list")


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty")
    return password_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hasher.verify(password, hashed_password)
