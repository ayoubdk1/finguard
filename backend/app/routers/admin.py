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



@router.get(
    "/admin/users",
    response_model=list[AdminUserResponse],
    status_code=status.HTTP_200_OK,
)
def admin_list_users(current_user: User = Depends(get_current_user)):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as session:
        users = session.scalars(
            select(User).order_by(User.created_at.desc())
        ).all()
        return users


@router.post(
    "/admin/users",
    response_model=AdminUserResponse,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_user(
    payload: AdminCreateUserRequest,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as session:
        existing = session.scalar(
            select(User).where(User.email == payload.email)
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        user = User(
            email=payload.email,
            full_name=payload.full_name,
            password_hash=hash_password(payload.password),
            role=payload.role,
            status=payload.status,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@router.patch(
    "/admin/users/{user_id}",
    response_model=AdminUserResponse,
    status_code=status.HTTP_200_OK,
)
def admin_update_user(
    user_id: UUID,
    payload: AdminUpdateUserRequest,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        if payload.full_name is not None:
            user.full_name = payload.full_name
        if payload.role is not None:
            user.role = payload.role
        if payload.status is not None:
            user.status = payload.status
            if payload.status != "ACTIVE":
                revoke_all_user_sessions(session, user.id)

        session.commit()
        session.refresh(user)
        return user


@router.post(
    "/admin/users/{user_id}/reset-password",
    status_code=status.HTTP_200_OK,
)
def admin_reset_user_password(
    user_id: UUID,
    payload: AdminResetPasswordRequest,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        user.password_hash = hash_password(payload.new_password)
        revoke_all_user_sessions(session, user.id)
        session.commit()
        return {"status": "password_reset_by_admin"}


@router.get(
    "/admin/users/{user_id}/login-history",
    response_model=list[LoginHistoryItem],
    status_code=status.HTTP_200_OK,
)
def admin_get_login_history(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        rows = session.scalars(
            select(LoginHistory)
            .where(LoginHistory.user_id == user_id)
            .order_by(LoginHistory.created_at.desc())
            .limit(50)
        ).all()
        return rows


@router.get(
    "/admin/users/{user_id}/sessions",
    response_model=SessionListResponse,
    status_code=status.HTTP_200_OK,
)
def admin_list_user_sessions(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        active_tokens = get_active_sessions_for_user(session, user_id)
        items = [SessionItem.model_validate(tok) for tok in active_tokens]
        return SessionListResponse(sessions=items, total_active=len(items))


@router.delete(
    "/admin/users/{user_id}/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def admin_revoke_user_session(
    user_id: UUID,
    session_id: UUID,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as session:
        revoked = revoke_session_by_id(session, session_id, user_id)
        if not revoked:
            raise HTTPException(status_code=404, detail="Session not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
