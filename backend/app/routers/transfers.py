import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError

from app.core.metrics import FRAUD_RISK_SCORE, TRANSFERS_TOTAL
from app.db.models import (
    Account,
    AccountType,
    ApprovalRequest,
    FraudAlert,
    FraudAlertStatus,
    LedgerEntry,
    Transaction,
    TransactionStatus,
    TransferAttempt,
    User,
)
from app.db.session import SessionLocal
from app.schemas.deposit import DepositCreate
from app.schemas.transfer import TransferCreate, TransferResponse
from app.security.dependencies import ensure_user_owns_account_id, get_current_user
from app.security.permissions import Permission, Role, has_permission
from app.services.audit import get_client_ip, get_request_id, record_audit_event
from app.services.fx import ExchangeRateNotFound, calculate_fx_conversion, get_latest_rate
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
from app.services.resilience import calculate_backoff_delay
from app.services.risk_assessment import assess_transaction_risk

logger = logging.getLogger("finguard.security")

router = APIRouter()



@router.post("/deposits", status_code=201)
def create_deposit(
    data: DepositCreate,
    request: Request,
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
            tx.idempotency_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
            record_audit_event(db, action="DEPOSIT_CREATED", resource_type="DEPOSIT", resource_id=tx.id, actor_id=current_user.id, ip_address=get_client_ip(request), request_id=get_request_id(request), details={"amount_cents": data.amount_cents})
            db.commit()
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        except AccountNotFound as exc:
            raise HTTPException(
                status_code=404,
                detail=str(exc),
            ) from exc

        except InvalidTransaction as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc

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
    if not has_permission(current_user.role, Permission.TRANSFER_CREATE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    ensure_user_owns_account_id(data.source_account_id, current_user, require_write=True)

    if data.source_account_id == data.destination_account_id:
        raise HTTPException(status_code=400, detail="Cannot transfer to the same account")

    tx_scope = f"{current_user.id}:POST:/transfers"
    tx_hash = compute_request_hash({
        "source_account_id": str(data.source_account_id),
        "destination_account_id": str(data.destination_account_id),
        "amount_cents": data.amount_cents,
        "description": data.description,
    })

    # 1.4 Replay before account locks and limit checks
    with SessionLocal() as db:
        replay_tx = db.scalar(
            select(Transaction).where(
                Transaction.idempotency_scope == tx_scope,
                Transaction.idempotency_key == idempotency_key,
            )
        )
        if replay_tx is not None:
            if replay_tx.request_hash is not None and replay_tx.request_hash != tx_hash:
                raise HTTPException(status_code=409, detail="Idempotency key used for different transaction")
            src_acct = db.get(Account, data.source_account_id)
            dst_acct = db.get(Account, data.destination_account_id)
            is_fx_replay = bool(src_acct and dst_acct and src_acct.currency != dst_acct.currency)
            rep_conv, rep_fee, rep_rate = None, None, None
            if is_fx_replay and src_acct and dst_acct:
                fx_del = db.scalar(
                    select(Transaction).where(
                        Transaction.idempotency_scope == f"{tx_scope}:fx_delivery",
                        Transaction.idempotency_key == f"{idempotency_key}:fx_delivery",
                    )
                )
                if fx_del is not None:
                    pos_del = [e for e in fx_del.entries if e.amount > 0]
                    if pos_del:
                        rep_conv = pos_del[0].amount
                fee_row = db.scalar(
                    select(LedgerEntry)
                    .join(Account, Account.id == LedgerEntry.account_id)
                    .where(
                        LedgerEntry.transaction_id == replay_tx.id,
                        Account.name == "SYSTEM_FX_FEE_REVENUE",
                    )
                )
                rep_fee = fee_row.amount if fee_row is not None else 0
                try:
                    rep_rate = float(Decimal(get_latest_rate(db, src_acct.currency, dst_acct.currency).rate) / Decimal(1_000_000))
                except ExchangeRateNotFound:
                    rep_rate = None
            return {
                "transaction_id": replay_tx.id,
                "status": replay_tx.status,
                "source_account_id": data.source_account_id,
                "destination_account_id": data.destination_account_id,
                "amount_cents": data.amount_cents,
                "currency": src_acct.currency if src_acct else "USD",
                "is_fx": is_fx_replay,
                "target_currency": dst_acct.currency if (is_fx_replay and dst_acct) else None,
                "converted_amount_cents": rep_conv,
                "fee_cents": rep_fee,
                "exchange_rate": rep_rate,
                "source_balance_cents": get_balance(db, data.source_account_id),
                "destination_balance_cents": get_balance(db, data.destination_account_id),
            }

    # 1.1 Retry loop for Postgres deadlock (40P01) / serialization failure (40001)
    max_db_attempts = 3
    for attempt in range(1, max_db_attempts + 1):
        with SessionLocal() as db:
            try:
                src_peek = db.get(Account, data.source_account_id)
                dst_peek = db.get(Account, data.destination_account_id)
                if src_peek is None or dst_peek is None:
                    raise HTTPException(status_code=404, detail="Account not found")

                is_fx = src_peek.currency != dst_peek.currency
                lock_ids = [data.source_account_id, data.destination_account_id]
                sys_fx_src_id = None
                sys_fx_dst_id = None
                fx_rate = None
                if is_fx:
                    try:
                        fx_rate = get_latest_rate(db, src_peek.currency, dst_peek.currency)
                    except ExchangeRateNotFound as exc:
                        raise HTTPException(status_code=400, detail=str(exc)) from exc
                    fx_src_acct = db.scalar(
                        select(Account).where(Account.name == "SYSTEM_FX", Account.currency == src_peek.currency)
                    )
                    fx_dst_acct = db.scalar(
                        select(Account).where(Account.name == "SYSTEM_FX", Account.currency == dst_peek.currency)
                    )
                    if fx_src_acct is None or fx_dst_acct is None:
                        raise HTTPException(status_code=409, detail="SYSTEM_FX clearing account not configured")
                    sys_fx_src_id = fx_src_acct.id
                    sys_fx_dst_id = fx_dst_acct.id

                # Lock all 2 or 4 accounts once in sorted UUID order
                ordered_ids = sorted(set(lock_ids))
                locked_accounts = db.scalars(
                    select(Account)
                    .where(Account.id.in_(ordered_ids))
                    .order_by(Account.id)
                    .with_for_update()
                ).all()
                acct_map = {a.id: a for a in locked_accounts}
                source = acct_map[data.source_account_id]
                destination = acct_map[data.destination_account_id]

                if source.account_type != AccountType.CUSTOMER or destination.account_type != AccountType.CUSTOMER:
                    raise HTTPException(status_code=400, detail="Transfers require customer accounts")

                try:
                    check_transfer_limits(db, source.id, data.amount_cents, currency=source.currency)
                except (TransactionLimitExceeded, DailyLimitExceeded) as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc

                # Pre-settlement fraud scoring (before ledger posting)
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
                        .select_from(TransferAttempt)
                        .where(
                            TransferAttempt.source_account_id == source.id,
                            TransferAttempt.created_at >= one_hour_ago,
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
                if risk.get("rules_decision") == "SIMULATED_HOLD":
                    raw_score = risk.get("ml_probability")
                    if raw_score is None:
                        raw_score = min(1.0, float(risk.get("rules_risk_score", 0)) / 100.0)
                    reasons = risk.get("reason_codes") or ["SIMULATED_HOLD"]
                    db.add(TransferAttempt(
                        source_account_id=source.id,
                        destination_account_id=destination.id,
                        amount_cents=data.amount_cents,
                        currency=source.currency,
                        reason="FRAUD_HOLD",
                    ))
                    db.add(FraudAlert(
                        transaction_id=None,
                        account_id=source.id,
                        risk_score=int(round(float(raw_score) * 1000)),
                        reasons=reasons,
                        status=FraudAlertStatus.PENDING.value,
                    ))
                    db.commit()
                    TRANSFERS_TOTAL.labels(currency=source.currency, status="BLOCKED").inc()
                    raise HTTPException(status_code=403, detail="Transfer blocked by fraud policy (SIMULATED_HOLD)")

                converted_amount_cents = None
                fee_cents = None
                effective_rate = None

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
                            source_account_id=source.id,  # noqa: B023
                            destination_account_id=destination.id,  # noqa: B023
                            amount_cents=data.amount_cents,
                            currency=source.currency,  # noqa: B023
                        ),
                    )
                else:
                    if fx_rate is None or sys_fx_src_id is None or sys_fx_dst_id is None:
                        raise HTTPException(status_code=500, detail="FX configuration missing")

                    converted_amount_cents, fee_cents, effective_rate = calculate_fx_conversion(
                        source_amount_cents=data.amount_cents,
                        base_currency=source.currency,  # noqa: B023
                        target_currency=destination.currency,
                        rate_scaled=fx_rate.rate,
                        fee_bps=fx_rate.fee_bps,
                    )

                    fee_account = None
                    if fee_cents > 0:
                        fee_account = db.scalar(
                            select(Account).where(
                                Account.name == "SYSTEM_FX_FEE_REVENUE",
                                Account.currency == source.currency,
                            )
                        )
                        if fee_account is None:
                            fee_account = Account(
                                name="SYSTEM_FX_FEE_REVENUE",
                                account_type=AccountType.SYSTEM,
                                currency=source.currency,
                            )
                            db.add(fee_account)
                            db.flush()

                    tx = post_transaction(
                        session=db,
                        idempotency_key=idempotency_key,
                        idempotency_scope=tx_scope,
                        request_hash=tx_hash,
                        entries=(
                            [
                                EntryInput(source.id, -data.amount_cents),
                                EntryInput(sys_fx_src_id, data.amount_cents - fee_cents),
                                EntryInput(
                                    fee_account.id,
                                    fee_cents,
                                ),
                            ]
                            if fee_cents > 0
                            else [
                                EntryInput(source.id, -data.amount_cents),
                                EntryInput(sys_fx_src_id, data.amount_cents),
                            ]
                        ),
                        description=data.description,
                        before_commit=lambda session, tx: enqueue_transfer_posted(
                            session=session,
                            transaction_id=tx.id,
                            source_account_id=source.id,  # noqa: B023
                            destination_account_id=destination.id,  # noqa: B023
                            amount_cents=data.amount_cents,
                            currency=source.currency,  # noqa: B023
                        ),
                        commit=False,
                    )
                    post_transaction(
                        session=db,
                        idempotency_key=f"{idempotency_key}:fx_delivery",
                        idempotency_scope=f"{tx_scope}:fx_delivery",
                        request_hash=tx_hash,
                        entries=[
                            EntryInput(sys_fx_dst_id, -converted_amount_cents),
                            EntryInput(destination.id, converted_amount_cents),
                        ],
                        description=f"FX from {source.id} ({source.currency}->{destination.currency})",
                        commit=False,
                    )
                    db.commit()

                TRANSFERS_TOTAL.labels(currency=source.currency, status="COMPLETED").inc()
                if risk.get("review_recommended"):
                    existing_alert = db.scalar(select(FraudAlert).where(FraudAlert.transaction_id == tx.id))
                    if existing_alert is None:
                        raw_score = risk.get("ml_probability")
                        if raw_score is None:
                            raw_score = min(1.0, float(risk.get("rules_risk_score", 0)) / 100.0)
                        db.add(
                            FraudAlert(
                                transaction_id=tx.id,
                                account_id=source.id,
                                risk_score=int(round(float(raw_score) * 1000)),
                                reasons=risk.get("reason_codes") or ["ML_ANOMALY"],
                                status=FraudAlertStatus.PENDING.value,
                            )
                        )
                        db.commit()
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
                    "source_balance_cents": get_balance(db, source.id),
                    "destination_balance_cents": get_balance(db, destination.id),
                }

            except IdempotencyConflict as exc:
                db.rollback()
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except InsufficientFunds as exc:
                db.rollback()
                src_acc = db.get(Account, data.source_account_id)
                db.add(TransferAttempt(
                    source_account_id=data.source_account_id,
                    destination_account_id=data.destination_account_id,
                    amount_cents=data.amount_cents,
                    currency=src_acc.currency if src_acc else "USD",
                    reason="INSUFFICIENT_FUNDS",
                ))
                db.commit()
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except AccountNotFound as exc:
                db.rollback()
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except InvalidTransaction as exc:
                db.rollback()
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except LedgerError as exc:
                db.rollback()
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except DBAPIError as exc:
                db.rollback()
                sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
                if sqlstate in ("40P01", "40001") and attempt < max_db_attempts:
                    time.sleep(calculate_backoff_delay(attempt, base_delay_seconds=0.02, max_delay_seconds=0.2, jitter_ratio=0.5))
                    continue
                if isinstance(exc, IntegrityError):
                    raise HTTPException(status_code=409, detail="Transfer conflicted with a concurrent update") from exc
                raise HTTPException(status_code=503, detail="Database temporarily unavailable; please retry") from exc
            except SQLAlchemyError as exc:
                db.rollback()
                raise HTTPException(status_code=503, detail="Database temporarily unavailable; please retry") from exc

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
    request: Request,
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
        if len(entries) < 2:
            raise HTTPException(status_code=400, detail="Cannot refund non-transfer transaction")

        debit_entry = entries[0]
        credit_entry = max(entries[1:], key=lambda e: e.amount)
        orig_source_id = debit_entry.account_id
        orig_dest_id = credit_entry.account_id
        transfer_amount = credit_entry.amount

        if original_tx.original_transaction_id is not None:
            raise HTTPException(status_code=409, detail="Cannot refund a refund transaction")

        tx_created = original_tx.created_at
        if tx_created.tzinfo is None:
            tx_created = tx_created.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - tx_created) > timedelta(days=30):
            raise HTTPException(status_code=422, detail="Refund window (30 days) has expired")

        fx_leg_peek = db.scalar(
            select(Transaction).where(
                Transaction.idempotency_scope == f"{original_tx.idempotency_scope}:fx_delivery",
                Transaction.idempotency_key == f"{original_tx.idempotency_key}:fx_delivery",
            )
        )
        recipient_acct_id = orig_dest_id
        if fx_leg_peek is not None:
            fx_e = sorted(fx_leg_peek.entries, key=lambda e: e.amount)
            if len(fx_e) == 2:
                recipient_acct_id = fx_e[1].account_id

        if current_user.role != Role.ADMIN:
            recipient_acct = db.get(Account, recipient_acct_id)
            if recipient_acct is None or recipient_acct.user_id != current_user.id:
                raise HTTPException(
                    status_code=403,
                    detail="Only the recipient or an admin can refund this transfer",
                )

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
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InsufficientFunds as exc:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail=f"Refund failed: recipient has insufficient funds ({exc})",
            ) from exc
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        record_audit_event(db, action="TRANSFER_REFUND", resource_type="TRANSACTION", resource_id=transfer_id, actor_id=current_user.id, ip_address=get_client_ip(request), request_id=get_request_id(request))
        db.commit()
        return TransferResponse(
            transaction_id=str(refund_tx.id),
            status=refund_tx.status.value,
            amount_cents=transfer_amount,
            source_account_id=str(orig_dest_id),
            destination_account_id=str(orig_source_id),
            created_at=refund_tx.created_at.isoformat(),
        )


@router.post("/deposits/request", status_code=201)
def request_deposit_approval(data: DepositCreate, request: Request, current_user: User = Depends(get_current_user)):
    if not has_permission(current_user.role, Permission.DEPOSIT_CREATE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    with SessionLocal() as db:
        req = ApprovalRequest(action_type="DEPOSIT", target_id=data.account_id, payload={"amount_cents": data.amount_cents}, requested_by=current_user.id)
        db.add(req)
        db.flush()
        record_audit_event(db, action="DEPOSIT_REQUESTED", resource_type="DEPOSIT", resource_id=req.id, actor_id=current_user.id, ip_address=get_client_ip(request), request_id=get_request_id(request), details={"amount_cents": data.amount_cents})
        db.commit()
        return {"id": str(req.id), "status": req.status}


@router.post("/deposits/{approval_id}/approve", status_code=200)
def approve_deposit_request(approval_id: UUID, request: Request, current_user: User = Depends(get_current_user)):
    if not has_permission(current_user.role, Permission.DEPOSIT_CREATE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    with SessionLocal() as db:
        req = db.get(ApprovalRequest, approval_id)
        if req is None or req.action_type != "DEPOSIT":
            raise HTTPException(status_code=404, detail="Deposit approval request not found")
        if req.status != "PENDING":
            raise HTTPException(status_code=409, detail="Approval request already resolved")
        if req.requested_by == current_user.id:
            raise HTTPException(status_code=409, detail="Four-eyes violation: requester cannot approve")
        target = db.get(Account, req.target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Target account not found")
        sys_acct = db.scalar(select(Account).where(Account.account_type == AccountType.SYSTEM, Account.currency == target.currency))
        if sys_acct is None:
            raise HTTPException(status_code=500, detail="System funding account not found")
        amt = int(req.payload["amount_cents"])
        tx = post_transaction(db, idempotency_key=f"dep-appr:{req.id}", idempotency_scope=f"deposit:{target.id}", description="Approved deposit", entries=[EntryInput(sys_acct.id, -amt), EntryInput(target.id, amt)])
        req.status = "APPROVED"
        req.approved_by = current_user.id
        req.resolved_at = datetime.now(timezone.utc)
        record_audit_event(db, action="DEPOSIT_APPROVED", resource_type="DEPOSIT", resource_id=tx.id, actor_id=current_user.id, ip_address=get_client_ip(request), request_id=get_request_id(request), details={"approval_id": str(req.id), "amount_cents": amt})
        db.commit()
        return {"id": str(req.id), "status": req.status, "transaction_id": str(tx.id)}
