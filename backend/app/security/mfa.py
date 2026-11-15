import base64
import hashlib
import hmac
import os
import secrets
import time

import pyotp
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

_DEV_FALLBACK_RAW = b"finguard-dev-only-mfa-key-32bytes!"


def _to_fernet_key(raw: str) -> bytes:
    raw_bytes = raw.strip().encode("utf-8")
    try:
        Fernet(raw_bytes)
        return raw_bytes
    except Exception:
        return base64.urlsafe_b64encode(hashlib.sha256(raw_bytes).digest())


def get_active_mfa_key_id() -> str:
    return os.getenv("FINGUARD_MFA_ENCRYPTION_KEY_ID", "k1").strip() or "k1"


def _get_fernet_keys() -> tuple[str, Fernet, MultiFernet]:
    env = os.getenv("FINGUARD_ENV", "development").lower()
    primary_raw = os.getenv("FINGUARD_MFA_ENCRYPTION_KEY", "").strip()
    if not primary_raw:
        if env == "production":
            raise RuntimeError("FINGUARD_MFA_ENCRYPTION_KEY must be set in production")
        primary_key = base64.urlsafe_b64encode(hashlib.sha256(_DEV_FALLBACK_RAW).digest())
    else:
        primary_key = _to_fernet_key(primary_raw)
    primary = Fernet(primary_key)
    fernets = [primary]
    prev_raw = os.getenv("FINGUARD_MFA_PREVIOUS_KEYS", "").strip()
    if prev_raw:
        for item in prev_raw.split(","):
            item = item.strip()
            if item:
                _, _, k = item.partition(":") if ":" in item else ("", "", item)
                fernets.append(Fernet(_to_fernet_key(k)))
    return get_active_mfa_key_id(), primary, MultiFernet(fernets)


def generate_mfa_secret() -> str:
    return pyotp.random_base32()


def generate_totp_uri(secret: str, email: str, issuer: str = "FinGuard") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp_with_step(secret: str, code: str, last_step: int | None = None, valid_window: int = 1, now: float | None = None) -> int | None:
    if not secret or not code or len(code.strip()) != 6 or not code.strip().isdigit():
        return None
    cleaned = code.strip()
    current_step = int(time.time() if now is None else now) // 30
    totp = pyotp.TOTP(secret)
    for offset in range(-valid_window, valid_window + 1):
        step = current_step + offset
        if hmac.compare_digest(totp.at(step * 30), cleaned):
            if last_step is not None and step <= last_step:
                return None
            return step
    return None


def verify_totp_code(secret: str, code: str) -> bool:
    return verify_totp_with_step(secret, code) is not None


def encrypt_mfa_secret(plain_secret: str) -> str:
    if plain_secret.startswith("enc:v2:"):
        return plain_secret
    kid, primary, _ = _get_fernet_keys()
    return f"enc:v2:{kid}:{primary.encrypt(plain_secret.encode('utf-8')).decode('ascii')}"


def decrypt_mfa_secret(stored_secret: str) -> str:
    if stored_secret.startswith("enc:v2:"):
        parts = stored_secret.split(":", 3)
        if len(parts) != 4:
            raise ValueError("Invalid MFA secret format")
        _, _, multi = _get_fernet_keys()
        try:
            return multi.decrypt(parts[3].encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Corrupted or tampered MFA secret") from exc
    if stored_secret.startswith("enc:v1:"):
        raise ValueError("Legacy v1 MFA secret must be migrated")
    return stored_secret


def generate_backup_codes(count: int = 10) -> list[str]:
    return [f"{(r := secrets.token_hex(4).upper())[:4]}-{r[4:]}" for _ in range(count)]


def hash_backup_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().replace("-", "").encode("utf-8")).hexdigest()


def verify_and_consume_backup_code(code: str, hashed_codes: list[str]) -> tuple[bool, list[str]]:
    cand = hash_backup_code(code)
    for idx, stored in enumerate(hashed_codes):
        if hmac.compare_digest(cand, stored):
            return True, hashed_codes[:idx] + hashed_codes[idx + 1:]
    return False, hashed_codes
