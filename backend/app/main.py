from datetime import datetime, timezone
from app.schemas.fraud import FraudAlertResponse, FraudResolutionRequest
from app.db.models import FraudAlert, FraudAlertStatus
from decimal import Decimal
from app.services.fx import get_latest_rate, calculate_fx_conversion, FXError, ExchangeRateNotFound
from app.services.limits import check_transfer_limits, TransactionLimitExceeded, DailyLimitExceeded

from uuid import UUID

from fastapi import FastAPI, HTTPException, Header
from sqlalchemy import text, select, func
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    User,
    Account,
    AccountType,
    LedgerEntry,
    Transaction,
    TransactionStatus,
    OutboxEvent,
    ProcessedEvent,
)
from app.db.session import engine, SessionLocal

from fastapi import Depends, Request, Response, status
from app.security.rate_limit import check_login_rate_limit
from sqlalchemy import select
from app.security.dependencies import ensure_user_owns_account_id, get_current_user
from app.security.permissions import Permission, has_permission
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    SessionItem,
    SessionListResponse,
    MfaLoginRequest,
    MfaSetupResponse,
    MfaVerifyRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)
from app.security.passwords import hash_password, verify_password
from app.security.mfa import generate_mfa_secret, generate_totp_uri, verify_totp_code
from app.security.tokens import (
    create_password_reset_token,
    revoke_all_user_sessions,
    verify_password_reset_token,
    create_access_token,
    create_mfa_token,
    get_active_sessions_for_user,
    verify_mfa_token,
    issue_refresh_token,
    revoke_session_by_id,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.schemas.user import UserCreate, UserResponse
from app.schemas.account import AccountCreate, AccountResponse
from app.schemas.deposit import DepositCreate
from app.schemas.transfer import TransferCreate, TransferResponse
from app.schemas.balance import BalanceResponse
from app.schemas.history import (
    TransactionHistoryItem,
    TransactionHistoryResponse,
)
from app.schemas.risk import RiskAssessmentRequest

from app.services.ledger import (
    EntryInput,
    post_transaction,
    get_balance,
    LedgerError,
    InvalidTransaction,
    AccountNotFound,
    InsufficientFunds,
)
from app.services.outbox import enqueue_transfer_posted
from app.services.risk_assessment import assess_transaction_risk


app = FastAPI(title="FinGuard API")


_METRICS_COUNTS: dict[tuple[str, str, int], int] = {}


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"

    # Use the route template (e.g. /accounts/{account_id}/balance), not the
    # raw URL, so every account UUID doesn't create a new metric series.
    route = request.scope.get("route")
    path = getattr(route, "path", "unmatched")

    key = (request.method, path, response.status_code)
    _METRICS_COUNTS[key] = _METRICS_COUNTS.get(key, 0) + 1
    return response


# ============================================================
# 1. HEALTH CHECK
# ============================================================

@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    return {"status": "ok"}


@app.get("/health/ready")
def readiness_check():
    checks: dict[str, str] = {}
    is_ready = True

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "error"
        is_ready = False

    try:
        from app.security.rate_limit import _get_redis_client
        r = _get_redis_client()
        if r is not None and r.ping():
            checks["redis"] = "ok"
        else:
            checks["redis"] = "disabled"
    except Exception:
        checks["redis"] = "degraded"

    if not is_ready:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": checks},
        )
    return {"status": "ready", "checks": checks}


# ============================================================
# 2. CREATE USER
# ============================================================

@app.post("/users", response_model=UserResponse, status_code=201)
def create_user(data: UserCreate):
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


# ============================================================
# 3. CREATE ACCOUNT
# ============================================================

@app.post("/accounts", response_model=AccountResponse, status_code=201)
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


# ============================================================
# 3. LIST CUSTOMER ACCOUNTS
# ============================================================

@app.get("/accounts", response_model=list[AccountResponse])
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


# ============================================================
# 4. SIMULATED DEPOSIT
# ============================================================

@app.post("/deposits", status_code=201)
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
        try:
            tx = post_transaction(
                session=db,
                idempotency_key=idempotency_key,
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


# ============================================================
# 5. SIMULATED TRANSFER + TRANSACTIONAL OUTBOX
# ============================================================

@app.post("/transfers", status_code=201)
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

        # 2. Find both accounts with pessimistic row lock on source account (race condition protection)
        source = db.scalar(
            select(Account)
            .where(Account.id == data.source_account_id)
            .with_for_update()
        )

        destination = db.get(
            Account,
            data.destination_account_id,
        )

        if source is None or destination is None:
            raise HTTPException(
                status_code=404,
                detail="Account not found",
            )

        # 3. Only CUSTOMER accounts
        if (
            source.account_type != AccountType.CUSTOMER
            or destination.account_type != AccountType.CUSTOMER
        ):
            raise HTTPException(
                status_code=400,
                detail="Transfers require customer accounts",
            )

        # 4b. Enforce per-transaction and rolling 24-hour limits
        try:
            check_transfer_limits(db, source.id, data.amount_cents)
        except (TransactionLimitExceeded, DailyLimitExceeded) as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            )

        # 5. Post ledger transaction: Same-Currency vs Cross-Currency FX
        is_fx = source.currency != destination.currency
        converted_amount_cents = None
        fee_cents = None
        effective_rate = None

        try:
            if not is_fx:
                tx = post_transaction(
                    session=db,
                    idempotency_key=idempotency_key,
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

                # Post source currency debit/credit to SYSTEM_FX
                tx = post_transaction(
                    session=db,
                    idempotency_key=idempotency_key,
                    entries=[
                        EntryInput(source.id, -data.amount_cents),
                        EntryInput(sys_fx_src.id, data.amount_cents),
                    ],
                    description=data.description,
                )

                # Post target currency delivery to destination
                post_transaction(
                    session=db,
                    idempotency_key=f"{idempotency_key}:fx_delivery",
                    entries=[
                        EntryInput(sys_fx_dst.id, -converted_amount_cents),
                        EntryInput(destination.id, converted_amount_cents),
                    ],
                    description=f"FX from {source.id} ({source.currency}->{destination.currency})",
                )

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


# ============================================================
# 6. ACCOUNT BALANCE
# ============================================================



# ============================================================
# 5b. REFUND TRANSFER
# ============================================================



# ============================================================
# 5c. FOREIGN EXCHANGE RATES
# ============================================================

@app.get("/fx/rates")
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


@app.post("/transfers/{transfer_id}/refund", response_model=TransferResponse, status_code=201)
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

        # Check for duplicate refund
        existing_refund = db.scalar(
            select(Transaction).where(
                Transaction.description == f"Refund of {original_tx.id}",
                Transaction.status == TransactionStatus.POSTED,
            )
        )
        if existing_refund:
            raise HTTPException(status_code=409, detail="Transaction has already been refunded")

        # Mirror entry: Debit original destination, Credit original source
        try:
            refund_tx = post_transaction(
                session=db,
                idempotency_key=idempotency_key,
                entries=[
                    EntryInput(orig_dest_id, -transfer_amount),
                    EntryInput(orig_source_id, transfer_amount),
                ],
                description=f"Refund of {original_tx.id}",
            )
        except InsufficientFunds as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Refund failed: recipient has insufficient funds ({exc})",
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return TransferResponse(
            transaction_id=str(refund_tx.id),
            status=refund_tx.status.value,
            amount_cents=transfer_amount,
            source_account_id=str(orig_dest_id),
            destination_account_id=str(orig_source_id),
            created_at=refund_tx.created_at.isoformat(),
        )


@app.get(
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


# ============================================================
# 7. ACCOUNT TRANSACTION HISTORY
# ============================================================

@app.get(
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


# ============================================================
# 8. FRAUD RISK ASSESSMENT
# ============================================================



# ============================================================
# 8b. FRAUD MANAGEMENT & INVESTIGATIONS
# ============================================================

@app.get("/fraud/alerts", response_model=list[FraudAlertResponse])
def list_fraud_alerts(
    status_filter: str | None = None,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.FRAUD_ALERT_READ):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as db:
        query = select(FraudAlert)
        if status_filter:
            query = query.where(FraudAlert.status == status_filter.upper())
        alerts = db.scalars(query.order_by(FraudAlert.created_at.desc())).all()
        return [
            FraudAlertResponse(
                id=a.id,
                transaction_id=a.transaction_id,
                account_id=a.account_id,
                risk_score=float(a.risk_score) / 1000.0,
                reasons=a.reasons,
                status=a.status.value if hasattr(a.status, 'value') else str(a.status),
                analyst_id=a.analyst_id,
                analyst_notes=a.analyst_notes,
                created_at=a.created_at,
                resolved_at=a.resolved_at,
            )
            for a in alerts
        ]


@app.post("/fraud/alerts/{alert_id}/investigate", response_model=FraudAlertResponse)
def start_investigation(
    alert_id: UUID,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.FRAUD_ALERT_RESOLVE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as db:
        alert = db.get(FraudAlert, alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="Fraud alert not found")

        alert.status = FraudAlertStatus.INVESTIGATING.value
        alert.analyst_id = current_user.id
        db.commit()
        db.refresh(alert)
        return FraudAlertResponse(
            id=alert.id,
            transaction_id=alert.transaction_id,
            account_id=alert.account_id,
            risk_score=float(alert.risk_score) / 1000.0,
            reasons=alert.reasons,
            status=alert.status if isinstance(alert.status, str) else alert.status.value,
            analyst_id=alert.analyst_id,
            analyst_notes=alert.analyst_notes,
            created_at=alert.created_at,
            resolved_at=alert.resolved_at,
        )


@app.post("/fraud/alerts/{alert_id}/resolve", response_model=FraudAlertResponse)
def resolve_alert(
    alert_id: UUID,
    payload: FraudResolutionRequest,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(current_user.role, Permission.FRAUD_ALERT_RESOLVE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as db:
        alert = db.get(FraudAlert, alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="Fraud alert not found")

        alert.status = payload.decision
        alert.analyst_id = current_user.id
        alert.analyst_notes = payload.analyst_notes
        alert.resolved_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(alert)
        return FraudAlertResponse(
            id=alert.id,
            transaction_id=alert.transaction_id,
            account_id=alert.account_id,
            risk_score=float(alert.risk_score) / 1000.0,
            reasons=alert.reasons,
            status=alert.status if isinstance(alert.status, str) else alert.status.value,
            analyst_id=alert.analyst_id,
            analyst_notes=alert.analyst_notes,
            created_at=alert.created_at,
            resolved_at=alert.resolved_at,
        )


@app.post("/risk/assess")
def assess_risk_endpoint(
    data: RiskAssessmentRequest,
    current_user: User = Depends(get_current_user),
):
    if not has_permission(
        current_user.role, Permission.RISK_ASSESS
    ):
        raise HTTPException(
            status_code=403, detail="Insufficient permissions"
        )
    result = assess_transaction_risk(
        amount_cents=data.amount_cents,
        transfers_last_10min=data.transfers_last_10min,
        account_age_minutes=data.account_age_minutes,
        failed_transfers_last_hour=data.failed_transfers_last_hour,
    )

    return result


# ============================================================
# 9. ADVANCED EVENT MONITORING
# ============================================================

@app.get("/monitoring/events")
def get_event_monitoring(
    current_user: User = Depends(get_current_user),
):
    if not has_permission(
        current_user.role, Permission.MONITORING_READ
    ):
        raise HTTPException(
            status_code=403, detail="Insufficient permissions"
        )
    with SessionLocal() as db:

        # =============================================
        # 1. EVENT STATISTICS
        # =============================================
        total_events = db.scalar(
            select(func.count())
            .select_from(OutboxEvent)
        ) or 0

        pending_events = db.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
        ) or 0

        published_events = db.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.published_at.is_not(None))
        ) or 0

        processed_events = db.scalar(
            select(func.count())
            .select_from(ProcessedEvent)
        ) or 0

        # =============================================
        # 2. RECENT EVENTS WITH CONSUMER STATUS (LEFT JOIN)
        # =============================================
        recent_rows = db.execute(
            select(OutboxEvent, ProcessedEvent.processed_at)
            .outerjoin(
                ProcessedEvent,
                OutboxEvent.id == ProcessedEvent.event_id,
            )
            .order_by(OutboxEvent.created_at.desc())
            .limit(10)
        ).all()

        recent_events = []
        for event, processed_at in recent_rows:
            if processed_at is not None:
                status = "PROCESSED"
            elif event.published_at is not None:
                status = "PUBLISHED"
            else:
                status = "PENDING"

            recent_events.append({
                "event_id": str(event.id),
                "event_type": event.event_type,
                "aggregate_id": str(event.aggregate_id),
                "created_at": event.created_at.isoformat(),
                "published_at": (
                    event.published_at.isoformat()
                    if event.published_at
                    else None
                ),
                "processed_at": (
                    processed_at.isoformat()
                    if processed_at
                    else None
                ),
                "publish_attempts": event.publish_attempts,
                "status": status,
            })

    return {
        "total_events": total_events,
        "pending_events": pending_events,
        "published_events": published_events,
        "processed_events": processed_events,
        "recent_events": recent_events,
    }

@app.post(
    "/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(payload: RegisterRequest):
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
            role="CUSTOMER",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@app.post(
    "/auth/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
def login_user(
    request: Request,
    payload: LoginRequest,
    _rate_limit: None = Depends(check_login_rate_limit),
):
    with SessionLocal() as session:
        user = session.scalar(
            select(User).where(User.email == payload.email)
        )
        if (
            user is None
            or not user.password_hash
            or not verify_password(payload.password, user.password_hash)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if user.mfa_enabled:
            mfa_tok = create_mfa_token(user.id)
            return TokenResponse(
                access_token="",
                mfa_required=True,
                mfa_token=mfa_tok,
            )

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


@app.post(
    "/auth/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
def refresh_access_token(request: Request, payload: RefreshRequest):
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


@app.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
def logout_user(payload: LogoutRequest):
    with SessionLocal() as session:
        revoke_refresh_token(session, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)






# ============================================================
# MULTI-FACTOR AUTHENTICATION (TOTP)
# ============================================================

@app.post(
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
        user.mfa_secret = secret
        session.commit()

        uri = generate_totp_uri(secret, user.email)
        return MfaSetupResponse(secret=secret, otpauth_uri=uri)


@app.post(
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

        if not verify_totp_code(user.mfa_secret, payload.code):
            raise HTTPException(status_code=400, detail="Invalid verification code")

        user.mfa_enabled = True
        session.commit()
        return {"status": "MFA successfully enabled"}


@app.post(
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

        if not verify_totp_code(user.mfa_secret, payload.code):
            raise HTTPException(status_code=400, detail="Invalid verification code")

        user.mfa_enabled = False
        user.mfa_secret = None
        session.commit()
        return {"status": "MFA successfully disabled"}


@app.post(
    "/auth/mfa/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
def mfa_login(
    request: Request,
    payload: MfaLoginRequest,
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

        if not verify_totp_code(user.mfa_secret, payload.code):
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


@app.get(
    "/auth/sessions",
    response_model=SessionListResponse,
    status_code=status.HTTP_200_OK,
)
def list_active_sessions(current_user: User = Depends(get_current_user)):
    with SessionLocal() as session:
        active_tokens = get_active_sessions_for_user(session, current_user.id)
        items = [SessionItem.model_validate(tok) for tok in active_tokens]
        return SessionListResponse(sessions=items, total_active=len(items))


@app.delete(
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


@app.post(
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

        return ForgotPasswordResponse(
            message="Si un compte correspond ? cet email, un jeton de r?initialisation a ?t? g?n?r?.",
            reset_token=reset_token,
        )


@app.post(
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


@app.get(
    "/auth/me",
    response_model=RegisterResponse,
    status_code=status.HTTP_200_OK,
)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user



@app.get("/metrics")
def prometheus_metrics():
    lines = [
        "# HELP finguard_http_requests_total Total HTTP requests handled",
        "# TYPE finguard_http_requests_total counter",
    ]
    for (method, path, code), count in sorted(_METRICS_COUNTS.items()):
        lines.append(
            f'finguard_http_requests_total{{method="{method}",path="{path}",status="{code}"}} {count}'
        )
    body = "\n".join(lines) + "\n"
    return Response(
        content=body,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
