
from fastapi import FastAPI, HTTPException, Header
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.db.models import User, Account, AccountType
  
from app.db.session import engine, SessionLocal
from app.schemas.user import UserCreate, UserResponse
from app.schemas.account import AccountCreate, AccountResponse
from sqlalchemy import select

from app.schemas.deposit import DepositCreate
from app.services.ledger import (
    EntryInput,
    post_transaction,
    get_balance,
    LedgerError,
    InvalidTransaction,
    AccountNotFound,
)

app = FastAPI(title="FinGuard API")


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/users", response_model=UserResponse, status_code=201)
def create_user(data: UserCreate):
    with SessionLocal() as db:
        user = User(
            email=data.email,
            full_name=data.full_name
        )

        db.add(user)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Email already registered"
            )

        db.refresh(user)
        return user
        
@app.post("/accounts", response_model=AccountResponse, status_code=201)
def create_account(data: AccountCreate):
    with SessionLocal() as db:

        # Verify that the user exists
        user = db.get(User, data.user_id)

        if user is None:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )

        # Create a CUSTOMER account
        account = Account(
            user_id=data.user_id,
            name=data.name,
            account_type=AccountType.CUSTOMER,
            currency=data.currency
        )

        db.add(account)
        db.commit()
        db.refresh(account)

        return account

@app.post("/deposits", status_code=201)
def create_deposit(
    data: DepositCreate,
    idempotency_key: str = Header(
        min_length=1,
        max_length=100,
        alias="Idempotency-Key"
    )
):
    with SessionLocal() as db:

        # 1. Find customer account
        account = db.get(Account, data.account_id)

        if account is None or account.account_type != AccountType.CUSTOMER:
            raise HTTPException(
                status_code=404,
                detail="Customer account not found"
            )

        # 2. Check currency
        if account.currency != "TND":
            raise HTTPException(
                status_code=400,
                detail="Only TND deposits are supported"
            )

        # 3. Find SYSTEM_FUNDING
        funding = db.scalar(
            select(Account).where(
                Account.name == "SYSTEM_FUNDING",
                Account.account_type == AccountType.SYSTEM,
                Account.currency == "TND"
            )
        )

        if funding is None:
            raise HTTPException(
                status_code=409,
                detail="TND SYSTEM_FUNDING account not found"
            )

        # 4. Post balanced ledger entries
        try:
            tx = post_transaction(
                session=db,
                idempotency_key=idempotency_key,
                entries=[
                    EntryInput(funding.id, -data.amount_cents),
                    EntryInput(account.id, data.amount_cents),
                ],
                description=data.description
            )
        except AccountNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except InvalidTransaction as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except LedgerError as exc:
            raise HTTPException(
                status_code=409,
                detail="Deposit could not be posted"
            ) from exc

        return {
            "transaction_id": tx.id,
            "status": tx.status,
            "account_id": account.id,
            "amount_cents": data.amount_cents,
            "currency": account.currency,
            "balance_cents": get_balance(db, account.id)
        }

