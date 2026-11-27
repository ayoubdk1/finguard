import base64
import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    Account,
    AccountType,
    LedgerEntry,
    Transaction,
    User,
)
from app.db.session import SessionLocal
from app.schemas.account import AccountCreate, AccountResponse, AccountStatusUpdate
from app.schemas.balance import BalanceResponse
from app.schemas.history import TransactionHistoryItem, TransactionHistoryResponse
from app.schemas.user import UserCreate, UserResponse
from app.security.dependencies import ensure_user_owns_account_id, get_current_user
from app.security.permissions import Permission, has_permission
from app.services.audit import get_client_ip, get_request_id, record_audit_event
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

        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Email already registered",
            ) from exc

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
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
):
    ensure_user_owns_account_id(account_id, current_user)

    with SessionLocal() as db:
        account = db.get(Account, account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")

        q = (
            select(LedgerEntry, Transaction)
            .join(Transaction, LedgerEntry.transaction_id == Transaction.id)
            .where(LedgerEntry.account_id == account_id)
        )
        if cursor:
            try:
                raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
                ts_str, eid_str = raw.split("|", 1)
                c_ts = datetime.fromisoformat(ts_str)
                c_id = int(eid_str)
            except Exception as exc:
                raise HTTPException(status_code=400, detail="Invalid pagination cursor") from exc
            q = q.where(
                or_(
                    Transaction.created_at < c_ts,
                    (Transaction.created_at == c_ts) & (LedgerEntry.id < c_id),
                )
            )
        else:
            q = q.offset(offset)

        rows = db.execute(
            q.order_by(Transaction.created_at.desc(), LedgerEntry.id.desc()).limit(limit + 1)
        ).all()

        has_more = len(rows) > limit
        page_rows = rows[:limit]
        next_cursor: str | None = None
        if has_more and page_rows:
            last_entry, last_tx = page_rows[-1]
            token = f"{last_tx.created_at.isoformat()}|{last_entry.id}"
            next_cursor = base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")

        history = [
            TransactionHistoryItem(
                transaction_id=tx.id,
                created_at=tx.created_at,
                description=tx.description,
                status=tx.status.value,
                amount_cents=entry.amount,
                currency=entry.currency,
            )
            for entry, tx in page_rows
        ]
        return TransactionHistoryResponse(
            account_id=account_id,
            transactions=history,
            next_cursor=next_cursor,
        )


@router.get("/accounts/{account_id}/statement")
def account_statement(
    account_id: UUID,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
):
    ensure_user_owns_account_id(account_id, current_user)
    with SessionLocal() as db:
        account = db.get(Account, account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")

        opening_balance = 0
        if from_date is not None:
            opening_balance = int(
                db.scalar(
                    select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                        LedgerEntry.account_id == account_id,
                        LedgerEntry.created_at < from_date,
                    )
                ) or 0
            )

        filters = [LedgerEntry.account_id == account_id]
        if from_date is not None:
            filters.append(LedgerEntry.created_at >= from_date)
        if to_date is not None:
            filters.append(LedgerEntry.created_at <= to_date)

        total_entries = int(db.scalar(select(func.count()).select_from(LedgerEntry).where(*filters)) or 0)
        period_sum = int(db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(*filters)) or 0)
        prior_sum = 0
        if offset > 0:
            sub = select(LedgerEntry.amount).where(*filters).order_by(LedgerEntry.created_at.asc(), LedgerEntry.id.asc()).limit(offset).subquery()
            prior_sum = int(db.scalar(select(func.coalesce(func.sum(sub.c.amount), 0))) or 0)

        rows = db.execute(
            select(LedgerEntry, Transaction)
            .join(Transaction, Transaction.id == LedgerEntry.transaction_id)
            .where(*filters)
            .order_by(LedgerEntry.created_at.asc(), LedgerEntry.id.asc())
            .limit(limit)
            .offset(offset)
        ).all()

        running = opening_balance + prior_sum
        entries = []
        for entry, tx in rows:
            running += int(entry.amount)
            entries.append({
                "entry_id": str(entry.id),
                "transaction_id": str(tx.id),
                "description": tx.description,
                "amount_cents": int(entry.amount),
                "currency": entry.currency,
                "running_balance_cents": running,
                "created_at": entry.created_at.isoformat(),
            })

        closing_balance = opening_balance + period_sum
        return {
            "account_id": str(account_id),
            "currency": account.currency,
            "opening_balance_cents": opening_balance,
            "closing_balance_cents": closing_balance,
            "derived_balance_check": True,
            "limit": limit,
            "offset": offset,
            "total_entries": total_entries,
            "entries": entries,
        }


@router.patch("/accounts/{account_id}/status", response_model=AccountResponse)
def update_account_status(
    account_id: UUID,
    payload: AccountStatusUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    if not (
        has_permission(current_user.role, Permission.USER_MANAGE)
        or has_permission(current_user.role, Permission.FRAUD_ALERT_RESOLVE)
    ):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with SessionLocal() as db:
        account = db.get(Account, account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        if account.account_type != AccountType.CUSTOMER:
            raise HTTPException(status_code=400, detail="Cannot change status of system accounts")
        if account.status == "CLOSED" and payload.status != "CLOSED":
            raise HTTPException(status_code=409, detail="Closed accounts cannot be reopened")
        if payload.status == "CLOSED" and get_balance(db, account.id) != 0:
            raise HTTPException(status_code=409, detail="Cannot close account with non-zero balance")

        old_status = account.status
        account.status = payload.status
        record_audit_event(
            db,
            action=f"ACCOUNT_STATUS_{payload.status}",
            resource_type="ACCOUNT",
            resource_id=account.id,
            actor_id=current_user.id,
            actor_role=current_user.role,
            ip_address=get_client_ip(request),
            request_id=get_request_id(request),
            before={"status": old_status},
            after={"status": payload.status},
        )
        db.commit()
        db.refresh(account)
        return account
