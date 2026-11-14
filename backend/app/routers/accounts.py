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



@router.post("/users", response_model=UserResponse, status_code=201)
def create_user(
    data: UserCreate,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    with SessionLocal() as db:

        user = User(
            email=data.email,
            full_name=data.full_name,
        )

        db.add(user)

        try:
            db.commit()

        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Email already registered",
            )

        db.refresh(user)
        return user


@router.post("/accounts", response_model=AccountResponse, status_code=201)
def create_account(
    data: AccountCreate,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(
        current_user.role, Permission.ACCOUNT_CREATE_OWN
    ):
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions",
        )
    if (
        not has_permission(
            current_user.role, Permission.ACCOUNT_CREATE_ANY
        )
        and data.user_id != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="Cannot create account for another user",
        )

    with SessionLocal() as db:

        user = db.get(User, data.user_id)

        if user is None:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        account = Account(
            user_id=data.user_id,
            name=data.name,
            account_type=AccountType.CUSTOMER,
            currency=data.currency,
        )

        db.add(account)
        db.commit()
        db.refresh(account)

        return account


@router.get("/accounts", response_model=list[AccountResponse])
def list_accounts(
    current_user: User = Depends(get_current_user),
):
    with SessionLocal() as db:

        query = select(Account).where(
            Account.account_type == AccountType.CUSTOMER
        )

        # Regular users can only see their own accounts.
        # Administrators can see all customer accounts.
        if not has_permission(
            current_user.role, Permission.ACCOUNT_READ_ALL
        ):
            query = query.where(
                Account.user_id == current_user.id
            )

        accounts = db.scalars(
            query.order_by(Account.created_at.desc())
        ).all()

        return accounts


@router.get(
    "/accounts/{account_id}/balance",
    response_model=BalanceResponse,
)
def account_balance(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
):
    ensure_user_owns_account_id(account_id, current_user)

    with SessionLocal() as db:

        # 1. Find account
        account = db.get(Account, account_id)

        if account is None:
            raise HTTPException(
                status_code=404,
                detail="Account not found",
            )

        # 2. Calculate balance from ledger
        balance = get_balance(db, account.id)

        # 3. Return balance
        return BalanceResponse(
            account_id=account.id,
            currency=account.currency,
            balance_cents=balance,
        )


@router.get(
    "/accounts/{account_id}/transactions",
    response_model=TransactionHistoryResponse,
)
def account_transactions(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
):
    ensure_user_owns_account_id(account_id, current_user)

    with SessionLocal() as db:

        # 1. Check account exists
        account = db.get(Account, account_id)

        if account is None:
            raise HTTPException(
                status_code=404,
                detail="Account not found",
            )

        # 2. Retrieve ledger entries and transactions
        rows = db.execute(
            select(
                LedgerEntry,
                Transaction,
            )
            .join(
                Transaction,
                LedgerEntry.transaction_id == Transaction.id,
            )
            .where(
                LedgerEntry.account_id == account_id
            )
            .order_by(
                Transaction.created_at.desc(),
                LedgerEntry.id.desc(),
            )
        ).all()

        # 3. Build transaction history
        history = [
            TransactionHistoryItem(
                transaction_id=tx.id,
                created_at=tx.created_at,
                description=tx.description,
                status=tx.status.value,
                amount_cents=entry.amount,
                currency=entry.currency,
            )
            for entry, tx in rows
        ]

        # 4. Return transaction history
        return TransactionHistoryResponse(
            account_id=account_id,
            transactions=history,
        )
