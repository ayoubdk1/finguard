import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    Account,
    AccountType,
    LedgerEntry,
    Transaction,
    User,
)
from app.db.session import SessionLocal
from app.schemas.account import AccountCreate, AccountResponse
from app.schemas.balance import BalanceResponse
from app.schemas.history import TransactionHistoryItem, TransactionHistoryResponse
from app.schemas.user import UserCreate, UserResponse
from app.security.dependencies import ensure_user_owns_account_id, get_current_user
from app.security.permissions import Permission, has_permission
from app.services.ledger import (
    get_balance,
)

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
