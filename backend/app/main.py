
from uuid import UUID

from fastapi import FastAPI, HTTPException, Header
from sqlalchemy import text, select
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    User,
    Account,
    AccountType,
    LedgerEntry,
    Transaction,
)
from app.db.session import engine, SessionLocal

from app.schemas.user import UserCreate, UserResponse
from app.schemas.account import AccountCreate, AccountResponse
from app.schemas.deposit import DepositCreate
from app.schemas.transfer import TransferCreate
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


# ============================================================
# 1. HEALTH CHECK
# ============================================================

@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    return {"status": "ok"}


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
def create_account(data: AccountCreate):
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
):
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

        # 2. Check currency
        if account.currency != "TND":
            raise HTTPException(
                status_code=400,
                detail="Only TND deposits are supported",
            )

        # 3. Find SYSTEM_FUNDING
        funding = db.scalar(
            select(Account).where(
                Account.name == "SYSTEM_FUNDING",
                Account.account_type == AccountType.SYSTEM,
                Account.currency == "TND",
            )
        )

        if funding is None:
            raise HTTPException(
                status_code=409,
                detail="TND SYSTEM_FUNDING account not found",
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
):
    with SessionLocal() as db:

        # 1. Prevent transfer to the same account
        if data.source_account_id == data.destination_account_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot transfer to the same account",
            )

        # 2. Find both accounts
        source = db.get(
            Account,
            data.source_account_id,
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

        # 4. Check currency
        if source.currency != destination.currency:
            raise HTTPException(
                status_code=400,
                detail="Accounts must use the same currency",
            )

        # 5. Post ledger transaction AND enqueue outbox event
        try:
            tx = post_transaction(
                session=db,
                idempotency_key=idempotency_key,
                entries=[
                    EntryInput(
                        source.id,
                        -data.amount_cents,
                    ),
                    EntryInput(
                        destination.id,
                        data.amount_cents,
                    ),
                ],
                description=data.description,

                # Outbox integration
                before_commit=lambda session, tx: enqueue_transfer_posted(
                    session=session,
                    transaction_id=tx.id,
                    source_account_id=source.id,
                    destination_account_id=destination.id,
                    amount_cents=data.amount_cents,
                    currency=source.currency,
                ),
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

        expected_entries = {
            (source.id, -data.amount_cents),
            (destination.id, data.amount_cents),
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

@app.get(
    "/accounts/{account_id}/balance",
    response_model=BalanceResponse,
)
def account_balance(account_id: UUID):
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
def account_transactions(account_id: UUID):
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

@app.post("/risk/assess")
def assess_risk_endpoint(data: RiskAssessmentRequest):
    result = assess_transaction_risk(
        amount_cents=data.amount_cents,
        transfers_last_10min=data.transfers_last_10min,
        account_age_minutes=data.account_age_minutes,
        failed_transfers_last_hour=data.failed_transfers_last_hour,
    )

    return result
