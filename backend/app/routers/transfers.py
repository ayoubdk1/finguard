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



@router.post("/deposits", status_code=201)
def create_deposit(
    data: DepositCreate,
    idempotency_key: str = Header(
        min_length=1,
        max_length=100,
        alias="Idempotency-Key",
    ),
    current_user: User = Depends(get_current_user),
):
    if not has_permission(
        current_user.role, Permission.DEPOSIT_CREATE
    ):
        raise HTTPException(
            status_code=403, detail="Insufficient permissions"
        )
    ensure_user_owns_account_id(
        data.account_id, current_user, require_write=True
    )

    with SessionLocal() as db:

        # 1. Find customer account
        account = db.get(Account, data.account_id)

        if (
            account is None
            or account.account_type != AccountType.CUSTOMER
        ):
            raise HTTPException(
                status_code=404,
                detail="Customer account not found",
            )

        # 2. Find SYSTEM_FUNDING for the customer's currency
        funding = db.scalar(
            select(Account).where(
                Account.name == "SYSTEM_FUNDING",
                Account.account_type == AccountType.SYSTEM,
                Account.currency == account.currency,
            )
        )

        if funding is None:
            raise HTTPException(
                status_code=409,
                detail=f"{account.currency} SYSTEM_FUNDING account not found",
            )

        # 4. Post balanced ledger entries
        # Deposits do NOT create TransferPosted events
        dep_scope = f"{current_user.id}:POST:/deposits"
        dep_hash = compute_request_hash({
            "account_id": str(data.account_id),
            "amount_cents": data.amount_cents,
            "description": data.description,
        })
        try:
            tx = post_transaction(
                session=db,
                idempotency_key=idempotency_key,
                idempotency_scope=dep_scope,
                request_hash=dep_hash,
                entries=[
                    EntryInput(
                        funding.id,
                        -data.amount_cents,
                    ),
                    EntryInput(
                        account.id,
                        data.amount_cents,
                    ),
                ],
                description=data.description,
            )
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        except AccountNotFound as exc:
            raise HTTPException(
                status_code=404,
                detail=str(exc),
            )

        except InvalidTransaction as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            )

        except LedgerError as exc:
            raise HTTPException(
                status_code=409,
                detail="Deposit could not be posted",
            ) from exc

        # 5. Reject reused keys with different deposit details
        rows = db.execute(
            select(
                LedgerEntry.account_id,
                LedgerEntry.amount,
            ).where(
                LedgerEntry.transaction_id == tx.id
            )
        ).all()

        actual_entries = set(rows)

        expected_entries = {
            (funding.id, -data.amount_cents),
            (account.id, data.amount_cents),
        }

        if (
            len(rows) != 2
            or actual_entries != expected_entries
            or tx.description != data.description
        ):
            raise HTTPException(
                status_code=409,
                detail="Idempotency key used for different deposit",
            )

        # 6. Return result
        return {
            "transaction_id": tx.id,
            "status": tx.status,
            "account_id": account.id,
            "amount_cents": data.amount_cents,
            "currency": account.currency,
            "balance_cents": get_balance(db, account.id),
        }


@router.post("/transfers", status_code=201)
def create_transfer(
    data: TransferCreate,
    idempotency_key: str = Header(
        min_length=1,
        max_length=100,
        alias="Idempotency-Key",
    ),
    current_user: User = Depends(get_current_user),
):
    if not has_permission(
        current_user.role, Permission.TRANSFER_CREATE
    ):
        raise HTTPException(
            status_code=403, detail="Insufficient permissions"
        )
    ensure_user_owns_account_id(
        data.source_account_id, current_user, require_write=True
    )

    with SessionLocal() as db:

        # 1. Prevent transfer to the same account
        if data.source_account_id == data.destination_account_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot transfer to the same account",
            )

        # 2. Lock both accounts once in deterministic UUID order (deadlock-free)
        ordered_ids = sorted([data.source_account_id, data.destination_account_id])
        locked_accounts = db.scalars(
            select(Account)
            .where(Account.id.in_(ordered_ids))
            .order_by(Account.id)
            .with_for_update()
        ).all()
        acct_map = {a.id: a for a in locked_accounts}
        source = acct_map.get(data.source_account_id)
        destination = acct_map.get(data.destination_account_id)

        if source is None or destination is None:
            raise HTTPException(
                status_code=404,
                detail="Account not found",
            )

        # 3. Ensure both accounts are customer accounts
        if (
            source.account_type != AccountType.CUSTOMER
            or destination.account_type != AccountType.CUSTOMER
        ):
            raise HTTPException(
                status_code=400,
                detail="Transfers require customer accounts",
            )

        # 4b. Enforce currency-aware per-transaction and rolling 24-hour limits
        try:
            check_transfer_limits(db, source.id, data.amount_cents, currency=source.currency)
        except (TransactionLimitExceeded, DailyLimitExceeded) as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            )

        # 5. Post ledger transaction: Same-Currency vs Atomic Cross-Currency FX
        is_fx = source.currency != destination.currency
        converted_amount_cents = None
        fee_cents = None
        effective_rate = None
        tx_scope = f"{current_user.id}:POST:/transfers"
        tx_hash = compute_request_hash({
            "source_account_id": str(data.source_account_id),
            "destination_account_id": str(data.destination_account_id),
            "amount_cents": data.amount_cents,
            "description": data.description,
        })

        try:
            if not is_fx:
                tx = post_transaction(
                    session=db,
                    idempotency_key=idempotency_key,
                    idempotency_scope=tx_scope,
                    request_hash=tx_hash,
                    entries=[
                        EntryInput(source.id, -data.amount_cents),
                        EntryInput(destination.id, data.amount_cents),
                    ],
                    description=data.description,
                    before_commit=lambda session, tx: enqueue_transfer_posted(
                        session=session,
                        transaction_id=tx.id,
                        source_account_id=source.id,
                        destination_account_id=destination.id,
                        amount_cents=data.amount_cents,
                        currency=source.currency,
                    ),
                )
            else:
                try:
                    fx_rate = get_latest_rate(db, source.currency, destination.currency)
                except ExchangeRateNotFound as exc:
                    raise HTTPException(status_code=400, detail=str(exc))

                converted_amount_cents, fee_cents, effective_rate = calculate_fx_conversion(
                    source_amount_cents=data.amount_cents,
                    base_currency=source.currency,
                    target_currency=destination.currency,
                    rate_scaled=fx_rate.rate,
                    fee_bps=fx_rate.fee_bps,
                )

                sys_fx_src = db.scalar(
                    select(Account).where(Account.name == "SYSTEM_FX", Account.currency == source.currency)
                )
                sys_fx_dst = db.scalar(
                    select(Account).where(Account.name == "SYSTEM_FX", Account.currency == destination.currency)
                )
                if sys_fx_src is None or sys_fx_dst is None:
                    raise HTTPException(status_code=500, detail="SYSTEM_FX clearing account not configured")

                tx = post_transaction(
                    session=db,
                    idempotency_key=idempotency_key,
                    idempotency_scope=tx_scope,
                    request_hash=tx_hash,
                    entries=[
                        EntryInput(source.id, -data.amount_cents),
                        EntryInput(sys_fx_src.id, data.amount_cents),
                    ],
                    description=data.description,
                    before_commit=lambda session, tx: enqueue_transfer_posted(
                        session=session,
                        transaction_id=tx.id,
                        source_account_id=source.id,
                        destination_account_id=destination.id,
                        amount_cents=data.amount_cents,
                        currency=source.currency,
                    ),
                    commit=False,
                )

                post_transaction(
                    session=db,
                    idempotency_key=f"{idempotency_key}:fx_delivery",
                    idempotency_scope=f"{tx_scope}:fx_delivery",
                    request_hash=tx_hash,
                    entries=[
                        EntryInput(sys_fx_dst.id, -converted_amount_cents),
                        EntryInput(destination.id, converted_amount_cents),
                    ],
                    description=f"FX from {source.id} ({source.currency}->{destination.currency})",
                    commit=False,
                )
                db.commit()

        except IdempotencyConflict as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail=str(exc))

        except InsufficientFunds as exc:
            raise HTTPException(
                status_code=409,
                detail=str(exc),
            )

        except AccountNotFound as exc:
            raise HTTPException(
                status_code=404,
                detail=str(exc),
            )

        except InvalidTransaction as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            )

        except LedgerError as exc:
            raise HTTPException(
                status_code=409,
                detail=str(exc),
            )

        # 6. Verify idempotency key was not reused
        # with different transaction details
        rows = db.execute(
            select(
                LedgerEntry.account_id,
                LedgerEntry.amount,
            ).where(
                LedgerEntry.transaction_id == tx.id
            )
        ).all()

        actual_entries = {
            (row[0], row[1])
            for row in rows
        }

        if not is_fx:
            expected_entries = {
                (source.id, -data.amount_cents),
                (destination.id, data.amount_cents),
            }
        else:
            expected_entries = {
                (source.id, -data.amount_cents),
                (sys_fx_src.id, data.amount_cents),
            }

        if (
            len(rows) != 2
            or actual_entries != expected_entries
            or tx.description != data.description
        ):
            raise HTTPException(
                status_code=409,
                detail="Idempotency key used for different transaction",
            )

        # 6b. Server-side fraud risk assessment & automatic FraudAlert creation
        now_utc = datetime.now(timezone.utc)
        ten_min_ago = now_utc - timedelta(minutes=10)
        one_hour_ago = now_utc - timedelta(hours=1)
        transfers_10m = int(
            db.scalar(
                select(func.count())
                .select_from(LedgerEntry)
                .join(Transaction, Transaction.id == LedgerEntry.transaction_id)
                .where(
                    LedgerEntry.account_id == source.id,
                    LedgerEntry.amount < 0,
                    Transaction.created_at >= ten_min_ago,
                )
            )
            or 0
        )
        src_created = source.created_at
        if src_created.tzinfo is None:
            src_created = src_created.replace(tzinfo=timezone.utc)
        account_age_min = max(0, int((now_utc - src_created).total_seconds() // 60))
        failed_1h = int(
            db.scalar(
                select(func.count())
                .select_from(LedgerEntry)
                .join(Transaction, Transaction.id == LedgerEntry.transaction_id)
                .where(
                    LedgerEntry.account_id == source.id,
                    Transaction.status == TransactionStatus.FAILED,
                    Transaction.created_at >= one_hour_ago,
                )
            )
            or 0
        )
        risk = assess_transaction_risk(
            amount_cents=data.amount_cents,
            transfers_last_10min=transfers_10m,
            account_age_minutes=account_age_min,
            failed_transfers_last_hour=failed_1h,
        )
        FRAUD_RISK_SCORE.observe(float(risk.get("rules_risk_score", 0)))
        TRANSFERS_TOTAL.labels(currency=source.currency, status="COMPLETED").inc()
        if risk.get("review_recommended"):
            existing_alert = db.scalar(
                select(FraudAlert).where(FraudAlert.transaction_id == tx.id)
            )
            if existing_alert is None:
                raw_score = risk.get("ml_probability")
                if raw_score is None:
                    raw_score = min(1.0, float(risk.get("rules_risk_score", 0)) / 100.0)
                reasons = risk.get("reason_codes") or ["ML_ANOMALY"]
                db.add(
                    FraudAlert(
                        transaction_id=tx.id,
                        account_id=source.id,
                        risk_score=int(round(float(raw_score) * 1000)),
                        reasons=reasons,
                        status=FraudAlertStatus.PENDING.value,
                    )
                )
                db.commit()

        # 7. Return result
        return {
            "transaction_id": tx.id,
            "status": tx.status,
            "source_account_id": source.id,
            "destination_account_id": destination.id,
            "amount_cents": data.amount_cents,
            "currency": source.currency,
            "is_fx": is_fx,
            "target_currency": destination.currency if is_fx else None,
            "converted_amount_cents": converted_amount_cents,
            "fee_cents": fee_cents,
            "exchange_rate": float(effective_rate) if effective_rate else None,
            "source_balance_cents": get_balance(
                db,
                source.id,
            ),
            "destination_balance_cents": get_balance(
                db,
                destination.id,
            ),
        }


@router.get("/fx/rates")
def list_exchange_rates():
    with SessionLocal() as db:
        from app.db.models import ExchangeRate
        rates = db.scalars(select(ExchangeRate).order_by(ExchangeRate.base_currency, ExchangeRate.target_currency)).all()
        return [
            {
                "base_currency": r.base_currency,
                "target_currency": r.target_currency,
                "rate": float(Decimal(r.rate) / Decimal(1_000_000)),
                "fee_bps": r.fee_bps,
            }
            for r in rates
        ]


@router.post("/transfers/{transfer_id}/refund", response_model=TransferResponse, status_code=201)
def refund_transfer(
    transfer_id: UUID,
    idempotency_key: str = Header(
        min_length=1,
        max_length=100,
        alias="Idempotency-Key",
    ),
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.TRANSFER_CREATE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as db:
        original_tx = db.get(Transaction, transfer_id)
        if original_tx is None:
            raise HTTPException(status_code=404, detail="Original transaction not found")

        if original_tx.status != TransactionStatus.POSTED:
            raise HTTPException(status_code=400, detail="Only posted transactions can be refunded")

        # Sort entries: debit entry (negative) and credit entry (positive)
        entries = sorted(original_tx.entries, key=lambda e: e.amount)
        if len(entries) != 2:
            raise HTTPException(status_code=400, detail="Cannot refund non-transfer transaction")

        debit_entry, credit_entry = entries[0], entries[1]
        orig_source_id = debit_entry.account_id
        orig_dest_id = credit_entry.account_id
        transfer_amount = credit_entry.amount

        # User must own original source account (or be ADMIN)
        ensure_user_owns_account_id(orig_source_id, current_user, require_write=True)

        refund_scope = f"{current_user.id}:POST:/transfers/{transfer_id}/refund"
        refund_hash = compute_request_hash({"transfer_id": str(transfer_id)})

        replay_tx = db.scalar(
            select(Transaction).where(
                Transaction.idempotency_scope == refund_scope,
                Transaction.idempotency_key == idempotency_key,
            )
        )
        if replay_tx is not None:
            if replay_tx.request_hash is not None and replay_tx.request_hash != refund_hash:
                raise HTTPException(status_code=409, detail="Idempotency key used for different refund")
            return TransferResponse(
                transaction_id=str(replay_tx.id),
                status=replay_tx.status.value,
                amount_cents=transfer_amount,
                source_account_id=str(orig_dest_id),
                destination_account_id=str(orig_source_id),
                created_at=replay_tx.created_at.isoformat(),
            )

        existing_refund = db.scalar(
            select(Transaction).where(
                Transaction.original_transaction_id == original_tx.id,
            )
        )
        if existing_refund:
            raise HTTPException(status_code=409, detail="Transaction has already been refunded")

        fx_leg = db.scalar(
            select(Transaction).where(
                Transaction.idempotency_scope == f"{original_tx.idempotency_scope}:fx_delivery",
                Transaction.idempotency_key == f"{original_tx.idempotency_key}:fx_delivery",
            )
        )

        try:
            if fx_leg is None:
                refund_tx = post_transaction(
                    session=db,
                    idempotency_key=idempotency_key,
                    idempotency_scope=refund_scope,
                    request_hash=refund_hash,
                    original_transaction_id=original_tx.id,
                    entries=[
                        EntryInput(orig_dest_id, -transfer_amount),
                        EntryInput(orig_source_id, transfer_amount),
                    ],
                    description=f"Refund of {original_tx.id}",
                )
            else:
                fx_entries = sorted(fx_leg.entries, key=lambda e: e.amount)
                fx_sys_dst_id = fx_entries[0].account_id
                fx_customer_dst_id = fx_entries[1].account_id
                fx_delivered_amount = fx_entries[1].amount

                refund_tx = post_transaction(
                    session=db,
                    idempotency_key=idempotency_key,
                    idempotency_scope=refund_scope,
                    request_hash=refund_hash,
                    original_transaction_id=original_tx.id,
                    entries=[
                        EntryInput(orig_dest_id, -transfer_amount),
                        EntryInput(orig_source_id, transfer_amount),
                    ],
                    description=f"Refund of {original_tx.id}",
                    commit=False,
                )
                post_transaction(
                    session=db,
                    idempotency_key=f"{idempotency_key}:fx_refund",
                    idempotency_scope=f"{refund_scope}:fx_refund",
                    request_hash=refund_hash,
                    entries=[
                        EntryInput(fx_customer_dst_id, -fx_delivered_amount),
                        EntryInput(fx_sys_dst_id, fx_delivered_amount),
                    ],
                    description=f"FX Refund of {original_tx.id}",
                    commit=False,
                )
                db.commit()
        except IdempotencyConflict as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail=str(exc))
        except InsufficientFunds as exc:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail=f"Refund failed: recipient has insufficient funds ({exc})",
            )
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(exc))

        return TransferResponse(
            transaction_id=str(refund_tx.id),
            status=refund_tx.status.value,
            amount_cents=transfer_amount,
            source_account_id=str(orig_dest_id),
            destination_account_id=str(orig_source_id),
            created_at=refund_tx.created_at.isoformat(),
        )
