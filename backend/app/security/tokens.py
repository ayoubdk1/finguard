import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "finguard"
JWT_AUDIENCE = "finguard-api"
ACCESS_TOKEN_EXPIRE_MINUTES = 15


def get_jwt_secret() -> str:
    secret = os.getenv("FINGUARD_JWT_SECRET")

    if not secret or len(secret) < 32:
        raise RuntimeError(
            "FINGUARD_JWT_SECRET must be configured "
            "with a secure random value"
        )

    return secret


def create_access_token(user_id: UUID) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        ),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "jti": str(uuid4()),
    }

    return jwt.encode(
        payload,
        get_jwt_secret(),
        algorithm=JWT_ALGORITHM,
    )


def verify_access_token(token: str) -> UUID:
    try:
        payload = jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={
                "require": [
                    "sub", "iat", "exp",
                    "iss", "aud", "jti",
                ]
            },
        )

        return UUID(payload["sub"])

    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError) as exc:
        raise ValueError(
            "Invalid or expired access token"
        ) from exc