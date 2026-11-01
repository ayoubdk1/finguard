import os
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db.models import Account, User
from app.db.session import SessionLocal
from app.security.tokens import verify_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        # Always require a token on /auth/me or when strict auth is enabled
        if request.url.path == "/auth/me" or os.getenv("FINGUARD_STRICT_AUTH") == "1":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        # Allow React Dashboard (DEMO MODE) when no Authorization header is sent
        return User(
            id=uuid4(),
            email="demo@finguard.local",
            full_name="Demo Mode",
            role="ADMIN",
        )

    try:
        user_id = verify_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        session.expunge(user)
        return user


def get_optional_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User | None:
    if credentials is None:
        return None
    return get_current_user(request, credentials)


def require_role(*allowed_roles: str):
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return role_checker


def verify_account_ownership(account: Account, current_user: User) -> None:
    if current_user.role == "ADMIN":
        return
    if account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this account",
        )


def ensure_user_owns_account_id(
    account_id: UUID | None,
    current_user: User,
) -> None:
    if account_id is None or current_user.role == "ADMIN":
        return
    with SessionLocal() as session:
        account = session.get(Account, account_id)
        if account is not None and account.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not own this account",
            )
