from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import os
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.currencies import SUPPORTED_CURRENCIES
from app.core.logging import configure_json_logging
from app.core.metrics import FRAUD_RISK_SCORE, TRANSFERS_TOTAL
from app.db.models import (
    Account,
    AccountType,
    ExchangeRate,
    FraudAlert,
    FraudAlertStatus,
    LedgerEntry,
    LoginHistory,
    OutboxEvent,
    ProcessedEvent,
    Transaction,
    TransactionStatus,
    User,
)
from app.db.session import SessionLocal, engine
from app.schemas.account import AccountCreate, AccountResponse
from app.schemas.auth import (
    AdminCreateUserRequest,
    AdminResetPasswordRequest,
    AdminUpdateUserRequest,
    AdminUserResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginHistoryItem,
    LoginRequest,
    LogoutRequest,
    MfaLoginRequest,
    MfaSetupResponse,
    MfaVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    SessionItem,
    SessionListResponse,
    TokenResponse,
)
from app.schemas.balance import BalanceResponse
from app.schemas.deposit import DepositCreate
from app.schemas.fraud import FraudAlertResponse, FraudResolutionRequest
from app.schemas.history import TransactionHistoryItem, TransactionHistoryResponse
from app.schemas.risk import RiskAssessmentRequest
from app.schemas.transfer import TransferCreate, TransferResponse
from app.schemas.user import UserCreate, UserResponse
from app.security.dependencies import ensure_user_owns_account_id, get_current_user
from app.security.mfa import (
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    generate_mfa_secret,
    generate_totp_uri,
    verify_totp_code,
)
from app.security.passwords import hash_password, verify_password
from app.security.permissions import Permission, has_permission
from app.security.rate_limit import check_login_rate_limit
from app.security.tokens import (
    create_access_token,
    create_mfa_token,
    create_password_reset_token,
    get_active_sessions_for_user,
    issue_refresh_token,
    revoke_all_user_sessions,
    revoke_refresh_token,
    revoke_session_by_id,
    rotate_refresh_token,
    verify_mfa_token,
    verify_password_reset_token,
)
from app.services.fx import ExchangeRateNotFound, FXError, calculate_fx_conversion, get_latest_rate
from app.services.ledger import (
    AccountNotFound,
    EntryInput,
    IdempotencyConflict,
    InsufficientFunds,
    InvalidTransaction,
    LedgerError,
    compute_request_hash,
    get_balance,
    post_transaction,
)
from app.services.limits import DailyLimitExceeded, TransactionLimitExceeded, check_transfer_limits
from app.services.outbox import enqueue_transfer_posted
from app.services.risk_assessment import assess_transaction_risk

logger = logging.getLogger("finguard.security")

router = APIRouter()



@router.post(
    "/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_403_FORBIDDEN,
)
def register_user(payload: RegisterRequest):
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Public registration is disabled. Contact an administrator.",
    )


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
def login_user(
    request: Request,
    payload: LoginRequest,
    _rate_limit: None = Depends(check_login_rate_limit),
):
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    with SessionLocal() as session:
        user = session.scalar(
            select(User).where(User.email == payload.email)
        )
        if (
            user is None
            or not user.password_hash
            or not verify_password(payload.password, user.password_hash)
        ):
            session.add(
                LoginHistory(
                    user_id=user.id if user else None,
                    email=payload.email,
                    ip_address=client_ip[:45] if client_ip else None,
                    user_agent=user_agent[:255] if user_agent else None,
                    success=False,
                    failure_reason="Invalid credentials",
                )
            )
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if getattr(user, "status", "ACTIVE") != "ACTIVE":
            session.add(
                LoginHistory(
                    user_id=user.id,
                    email=user.email,
                    ip_address=client_ip[:45] if client_ip else None,
                    user_agent=user_agent[:255] if user_agent else None,
                    success=False,
                    failure_reason=f"Account {user.status.lower()}",
                )
            )
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is not active. Contact an administrator.",
            )

        if user.mfa_enabled:
            session.add(
                LoginHistory(
                    user_id=user.id,
                    email=user.email,
                    ip_address=client_ip[:45] if client_ip else None,
                    user_agent=user_agent[:255] if user_agent else None,
                    success=True,
                    failure_reason="MFA pending",
                )
            )
            session.commit()
            mfa_tok = create_mfa_token(user.id)
            return TokenResponse(
                access_token="",
                mfa_required=True,
                mfa_token=mfa_tok,
            )

        token = create_access_token(user.id)
        refresh_token, _ = issue_refresh_token(
            session,
            user.id,
            user_agent=user_agent,
            ip_address=client_ip,
        )
        session.add(
            LoginHistory(
                user_id=user.id,
                email=user.email,
                ip_address=client_ip[:45] if client_ip else None,
                user_agent=user_agent[:255] if user_agent else None,
                success=True,
            )
        )
        session.commit()
        return TokenResponse(
            access_token=token,
            refresh_token=refresh_token,
        )


@router.post(
    "/auth/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
def refresh_access_token(
    request: Request,
    payload: RefreshRequest,
    _rate_limit: None = Depends(check_login_rate_limit),
):
    with SessionLocal() as session:
        try:
            client_ip = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")
            user_id, new_refresh = rotate_refresh_token(
                session,
                payload.refresh_token,
                user_agent=user_agent,
                ip_address=client_ip,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        access_token = create_access_token(user_id)
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh,
        )


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
def logout_user(payload: LogoutRequest):
    with SessionLocal() as session:
        revoke_refresh_token(session, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/auth/mfa/setup",
    response_model=MfaSetupResponse,
    status_code=status.HTTP_200_OK,
)
def mfa_setup(current_user: User = Depends(get_current_user)):
    with SessionLocal() as session:
        user = session.get(User, current_user.id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        secret = generate_mfa_secret()
        user.mfa_secret = encrypt_mfa_secret(secret)
        session.commit()

        uri = generate_totp_uri(secret, user.email)
        return MfaSetupResponse(secret=secret, otpauth_uri=uri)


@router.post(
    "/auth/mfa/enable",
    status_code=status.HTTP_200_OK,
)
def mfa_enable(
    payload: MfaVerifyRequest,
    current_user: User = Depends(get_current_user),
):
    with SessionLocal() as session:
        user = session.get(User, current_user.id)
        if user is None or not user.mfa_secret:
            raise HTTPException(status_code=400, detail="MFA setup has not been initiated")

        if not verify_totp_code(decrypt_mfa_secret(user.mfa_secret), payload.code):
            raise HTTPException(status_code=400, detail="Invalid verification code")

        user.mfa_enabled = True
        session.commit()
        return {"status": "MFA successfully enabled"}


@router.post(
    "/auth/mfa/disable",
    status_code=status.HTTP_200_OK,
)
def mfa_disable(
    payload: MfaVerifyRequest,
    current_user: User = Depends(get_current_user),
):
    with SessionLocal() as session:
        user = session.get(User, current_user.id)
        if user is None or not user.mfa_enabled or not user.mfa_secret:
            raise HTTPException(status_code=400, detail="MFA is not enabled")

        if not verify_totp_code(decrypt_mfa_secret(user.mfa_secret), payload.code):
            raise HTTPException(status_code=400, detail="Invalid verification code")

        user.mfa_enabled = False
        user.mfa_secret = None
        session.commit()
        return {"status": "MFA successfully disabled"}


@router.post(
    "/auth/mfa/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
def mfa_login(
    request: Request,
    payload: MfaLoginRequest,
    _rate_limit: None = Depends(check_login_rate_limit),
):
    try:
        user_id = verify_mfa_token(payload.mfa_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None or not user.mfa_enabled or not user.mfa_secret:
            raise HTTPException(status_code=400, detail="MFA not active for this account")

        if not verify_totp_code(decrypt_mfa_secret(user.mfa_secret), payload.code):
            raise HTTPException(status_code=401, detail="Invalid MFA code")

        token = create_access_token(user.id)
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        refresh_token, _ = issue_refresh_token(
            session,
            user.id,
            user_agent=user_agent,
            ip_address=client_ip,
        )
        session.commit()
        return TokenResponse(
            access_token=token,
            refresh_token=refresh_token,
        )


@router.get(
    "/auth/sessions",
    response_model=SessionListResponse,
    status_code=status.HTTP_200_OK,
)
def list_active_sessions(current_user: User = Depends(get_current_user)):
    with SessionLocal() as session:
        active_tokens = get_active_sessions_for_user(session, current_user.id)
        items = [SessionItem.model_validate(tok) for tok in active_tokens]
        return SessionListResponse(sessions=items, total_active=len(items))


@router.delete(
    "/auth/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
):
    with SessionLocal() as session:
        revoked = revoke_session_by_id(session, session_id, current_user.id)
        if not revoked:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/auth/forgot-password",
    response_model=ForgotPasswordResponse,
    status_code=status.HTTP_200_OK,
)
def forgot_password(
    payload: ForgotPasswordRequest,
    _rate_limit: None = Depends(check_login_rate_limit),
):
    with SessionLocal() as session:
        user = session.scalar(
            select(User).where(User.email == payload.email)
        )
        reset_token: str | None = None
        if user is not None and user.password_hash:
            reset_token = create_password_reset_token(
                user_id=user.id,
                email=user.email,
                current_password_hash=user.password_hash,
            )

        if reset_token:
            logger.info("Password reset token generated for %s", payload.email)
        expose_token = os.getenv("FINGUARD_EXPOSE_RESET_TOKEN") == "1"
        return ForgotPasswordResponse(
            message="Si un compte correspond ? cet email, un lien de r?initialisation a ?t? envoy?.",
            reset_token=reset_token if expose_token else None,
        )


@router.post(
    "/auth/reset-password",
    status_code=status.HTTP_200_OK,
)
def reset_password(
    payload: ResetPasswordRequest,
    _rate_limit: None = Depends(check_login_rate_limit),
):
    import hashlib as _hashlib
    import jwt as _jwt

    try:
        claims = verify_password_reset_token(payload.reset_token)
        user_id = UUID(str(claims["sub"]))
    except (_jwt.InvalidTokenError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token",
        ) from exc

    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None or not user.password_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired password reset token",
            )

        expected_fgp = _hashlib.sha256(
            user.password_hash.encode("utf-8")
        ).hexdigest()[:16]
        if claims.get("pwd_fgp") != expected_fgp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password reset token has already been used",
            )

        user.password_hash = hash_password(payload.new_password)
        revoke_all_user_sessions(session, user.id)
        session.commit()

        return {"status": "password_reset_success"}


@router.get(
    "/auth/me",
    response_model=RegisterResponse,
    status_code=status.HTTP_200_OK,
)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user
