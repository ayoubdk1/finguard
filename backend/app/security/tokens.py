import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import RefreshToken

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "finguard"
JWT_AUDIENCE = "finguard-api"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


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


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_refresh_token(
    session: Session,
    user_id: UUID,
    family_id: UUID | None = None,
) -> tuple[str, RefreshToken]:
    raw_token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    db_token = RefreshToken(
        id=uuid4(),
        user_id=user_id,
        family_id=family_id or uuid4(),
        token_hash=hash_refresh_token(raw_token),
        expires_at=now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    session.add(db_token)
    session.flush()
    return raw_token, db_token


def rotate_refresh_token(
    session: Session,
    raw_token: str,
) -> tuple[UUID, str]:
    now = datetime.now(timezone.utc)
    token_hash = hash_refresh_token(raw_token)
    db_token = session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    if db_token is None:
        raise ValueError("Invalid refresh token")

    if db_token.replaced_by_id is not None:
        session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == db_token.family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        session.commit()
        raise ValueError(
            "Refresh token reuse detected; session family revoked"
        )

    if db_token.revoked_at is not None:
        raise ValueError("Refresh token has been revoked")

    expires_at = db_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise ValueError("Refresh token has expired")

    new_raw, new_db_token = issue_refresh_token(
        session,
        user_id=db_token.user_id,
        family_id=db_token.family_id,
    )
    db_token.revoked_at = now
    db_token.replaced_by_id = new_db_token.id
    session.commit()
    return db_token.user_id, new_raw


def revoke_refresh_token(session: Session, raw_token: str) -> bool:
    now = datetime.now(timezone.utc)
    token_hash = hash_refresh_token(raw_token)
    db_token = session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    if db_token is None:
        return False

    session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.family_id == db_token.family_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    session.commit()
    return True
