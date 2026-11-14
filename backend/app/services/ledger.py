import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    AccountType,
    LedgerEntry,
    Transaction,
    TransactionStatus,
)


class LedgerError(Exception):
    """Base error for ledger posting failures."""


class InvalidTransaction(LedgerError):
    """Raised when a transaction violates double-entry rules."""


class AccountNotFound(LedgerError):
    """Raised when one or more accounts do not exist."""


class InsufficientFunds(LedgerError):
    """Raised when a customer account would go below zero."""


class IdempotencyConflict(LedgerError):
    """Raised when an idempotency key is reused with a different request payload."""


@dataclass(frozen=True)
class EntryInput:
    account_id: uuid.UUID
    amount: int  # signed cents; negative = debit, positive = credit


def compute_request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_balance(session: Session, account_id: uuid.UUID) -> int:
    """Rule I4: the balance is always derived from the ledger."""
    val = session.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.account_id == account_id
        )
    )
    return int(val or 0)



def _find_by_key(session: Session, key: str, scope: str = "global") -> Transaction | None:
    return session.scalar(
        select(Transaction).where(
            Transaction.idempotency_scope == scope,
            Transaction.idempotency_key == key,
        )
    )


def post_transaction(
    session: Session,
    idempotency_key: str,
    entries: list[EntryInput],
    description: str = "",
    before_commit: Callable[[Session, Transaction], Any] | None = None,
    *,
    idempotency_scope: str = "global",
    request_hash: str | None = None,
    original_transaction_id: uuid.UUID | None = None,
    commit: bool = True,
) -> Transaction:
    # 1. Validate the request itself (R1, R3, I1, I9)
    if not idempotency_key:
        raise InvalidTransaction("idempotency key is required")
    if len(entries) < 2:
        raise InvalidTransaction("a transaction needs at least 2 entries")

    for e in entries:
        if not isinstance(e.amount, int) or isinstance(e.amount, bool):
            raise InvalidTransaction("amounts must be integers in cents")
        if e.amount == 0:
            raise InvalidTransaction("amounts must be non-zero")

    if sum(e.amount for e in entries) != 0:
        raise InvalidTransaction("transaction is not balanced")

    # 2. Idempotency (I7): same (scope, key) returns the original transaction or raises on hash mismatch
    existing = _find_by_key(session, idempotency_key, scope=idempotency_scope)
    if existing is not None:
        if request_hash is not None and existing.request_hash is not None and existing.request_hash != request_hash:
            raise IdempotencyConflict("Idempotency key used for different request payload")
        return existing

    # 3. Lock the accounts in a fixed UUID order to avoid deadlocks
    account_ids = sorted({e.account_id for e in entries})
    accounts = session.scalars(
        select(Account).where(Account.id.in_(account_ids)).order_by(Account.id).with_for_update()
    ).all()

    if len(accounts) != len(account_ids):
        if commit:
            session.rollback()
        raise AccountNotFound("one or more accounts do not exist")

    by_id = {a.id: a for a in accounts}

    # 4. One currency per transaction (I2)
    if len({a.currency for a in accounts}) != 1:
        if commit:
            session.rollback()
        raise InvalidTransaction("transaction mixes currencies")

    # 5. No overdraft on customer accounts (I5)
    deltas: dict[uuid.UUID, int] = defaultdict(int)
    for e in entries:
        deltas[e.account_id] += e.amount

    for acct in accounts:
        if acct.account_type == AccountType.CUSTOMER and deltas[acct.id] < 0:
            if get_balance(session, acct.id) + deltas[acct.id] < 0:
                if commit:
                    session.rollback()
                raise InsufficientFunds(f"insufficient funds in account {acct.id}")

    # 6. Write ledger entries and outbox event atomically (I6)
    tx = Transaction(
        idempotency_key=idempotency_key,
        idempotency_scope=idempotency_scope,
        request_hash=request_hash,
        original_transaction_id=original_transaction_id,
        description=description,
        status=TransactionStatus.POSTED,
    )

    try:
        session.add(tx)
        session.flush()
        for e in entries:
            session.add(
                LedgerEntry(
                    transaction_id=tx.id,
                    account_id=e.account_id,
                    amount=e.amount,
                    currency=by_id[e.account_id].currency,
                )
            )
        session.flush()
        if before_commit is not None:
            before_commit(session, tx)
        if commit:
            session.commit()
    except IntegrityError as exc:
        if commit:
            session.rollback()
            winner = _find_by_key(session, idempotency_key, scope=idempotency_scope)
            if winner is not None:
                if request_hash is not None and winner.request_hash is not None and winner.request_hash != request_hash:
                    raise IdempotencyConflict("Idempotency key used for different request payload") from exc
                return winner
        raise LedgerError(str(exc.orig)) from exc
    except DBAPIError as exc:
        if commit:
            session.rollback()
        raise LedgerError(str(exc.orig)) from exc
    except Exception:
        if commit:
            session.rollback()
        raise

    return tx
