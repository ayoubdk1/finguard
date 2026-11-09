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
