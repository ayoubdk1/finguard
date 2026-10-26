import uuid
from collections import defaultdict
from dataclasses import dataclass
from collections.abc import Callable
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
    """Base class for all ledger errors."""


class InvalidTransaction(LedgerError):
    pass


class AccountNotFound(LedgerError):
    pass


class InsufficientFunds(LedgerError):
    pass


@dataclass(frozen=True)
class EntryInput:
    account_id: uuid.UUID
    amount: int  # cents; negative = debit, positive = credit


def get_balance(session: Session, account_id: uuid.UUID) -> int:
    """Rule I4: the balance is always derived from the ledger."""
    return session.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.account_id == account_id
        )
    )


def _find_by_key(session: Session, key: str) -> Transaction | None:
    return session.scalar(select(Transaction).where(Transaction.idempotency_key == key))


def post_transaction(
    session: Session,
    idempotency_key: str,
    entries: list[EntryInput],
    description: str = "",
    before_commit: Callable[[Session, Transaction], None] | None = None,
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

    # 2. Idempotency (I7): same key returns the original transaction
    existing = _find_by_key(session, idempotency_key)
    if existing is not None:
        return existing

    # 3. Lock the accounts in a fixed order to avoid deadlocks
    account_ids = sorted({e.account_id for e in entries})
    accounts = session.scalars(
        select(Account).where(Account.id.in_(account_ids)).order_by(Account.id).with_for_update()
    ).all()
    if len(accounts) != len(account_ids):
        session.rollback()
        raise AccountNotFound("one or more accounts do not exist")
    by_id = {a.id: a for a in accounts}

    # 4. One currency per transaction (I2)
    if len({a.currency for a in accounts}) != 1:
        session.rollback()
        raise InvalidTransaction("transaction mixes currencies")

    # 5. No overdraft on customer accounts (I5)
    deltas: dict[uuid.UUID, int] = defaultdict(int)
    for e in entries:
        deltas[e.account_id] += e.amount
    for acct in accounts:
        if acct.account_type == AccountType.CUSTOMER and deltas[acct.id] < 0:
            if get_balance(session, acct.id) + deltas[acct.id] < 0:
                session.rollback()
                raise InsufficientFunds(f"insufficient funds in account {acct.id}")


    # 6. Write ledger entries and outbox event atomically (I6)
    tx = Transaction(
        idempotency_key=idempotency_key,
        description=description,
        status=TransactionStatus.POSTED,
    )

    try:
        # Create the transaction
        session.add(tx)
        session.flush()

        # Create ledger entries
        for e in entries:
            session.add(
                LedgerEntry(
                    transaction_id=tx.id,
                    account_id=e.account_id,
                    amount=e.amount,
                    currency=by_id[e.account_id].currency,
                )
            )

        # Write ledger entries before the callback
        session.flush()

        # Create outbox event in the SAME database session
        if before_commit is not None:
            before_commit(session, tx)

        # Commit ledger + outbox together
        session.commit()

    except IntegrityError as exc:
        session.rollback()

        # Concurrent requests with the same key:
        # return the transaction that was committed first
        winner = _find_by_key(session, idempotency_key)
        if winner is not None:
            return winner

        raise LedgerError(str(exc.orig)) from exc

    except DBAPIError as exc:
        session.rollback()
        raise LedgerError(str(exc.orig)) from exc

    except Exception:
        session.rollback()
        raise

    return tx
