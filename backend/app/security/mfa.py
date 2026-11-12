import pyotp


def generate_mfa_secret() -> str:
    return pyotp.random_base32()


def generate_totp_uri(secret: str, email: str, issuer: str = "FinGuard") -> str:
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer)


def verify_totp_code(secret: str, code: str) -> bool:
    if not secret or not code or len(code.strip()) != 6:
        return False
    totp = pyotp.TOTP(secret)
    # valid_window=1 allows a +/- 30s clock skew window
    return bool(totp.verify(code.strip(), valid_window=1))

import base64
import hashlib
import hmac
import os
from app.security.tokens import get_jwt_secret


def _derive_encryption_key() -> bytes:
    raw = os.getenv("FINGUARD_MFA_ENCRYPTION_KEY") or get_jwt_secret()
    return hashlib.sha256(raw.encode("utf-8")).digest()


def encrypt_mfa_secret(plain_secret: str) -> str:
    if plain_secret.startswith("enc:v1:"):
        return plain_secret
    key = _derive_encryption_key()
    nonce = os.urandom(16)
    stream = hashlib.pbkdf2_hmac("sha256", key, nonce, 10_000, dklen=len(plain_secret))
    cipher_bytes = bytes(a ^ b for a, b in zip(plain_secret.encode("utf-8"), stream))
    mac = hmac.new(key, nonce + cipher_bytes, hashlib.sha256).digest()[:16]
    blob = base64.urlsafe_b64encode(nonce + mac + cipher_bytes).decode("ascii")
    return f"enc:v1:{blob}"


def decrypt_mfa_secret(stored_secret: str) -> str:
    if not stored_secret.startswith("enc:v1:"):
        return stored_secret
    key = _derive_encryption_key()
    raw = base64.urlsafe_b64decode(stored_secret[len("enc:v1:"):].encode("ascii"))
    nonce, mac, cipher_bytes = raw[:16], raw[16:32], raw[32:]
    expected_mac = hmac.new(key, nonce + cipher_bytes, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(mac, expected_mac):
        raise ValueError("Corrupted or tampered MFA secret")
    stream = hashlib.pbkdf2_hmac("sha256", key, nonce, 10_000, dklen=len(cipher_bytes))
    plain_bytes = bytes(a ^ b for a, b in zip(cipher_bytes, stream))
    return plain_bytes.decode("utf-8")
