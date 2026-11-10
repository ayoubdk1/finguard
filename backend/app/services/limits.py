import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import LedgerEntry, Transaction, TransactionStatus

# Default Fintech Limits (in cents / minor units)
MAX_TRANSACTION_AMOUNT_CENTS = 1_000_000      # 10,000.00
DAILY_TRANSFER_LIMIT_CENTS = 5_000_000         # 50,000.00


class TransactionSecurityError(Exception):
    """Base exception for transaction security violations."""
    pass


class TransactionLimitExceeded(TransactionSecurityError):
    pass


class DailyLimitExceeded(TransactionSecurityError):
    pass


def get_daily_transferred_amount(session: Session, source_account_id: uuid.UUID) -> int:
    """Sum all outgoing transfer debits from this account in the last 24 hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    result = session.scalar(
        select(func.coalesce(func.sum(-LedgerEntry.amount), 0))
        .join(Transaction, Transaction.id == LedgerEntry.transaction_id)
        .where(
            LedgerEntry.account_id == source_account_id,
            LedgerEntry.amount < 0,
            Transaction.status == TransactionStatus.POSTED,
            Transaction.created_at >= cutoff,
        )
    )
    return int(result or 0)


def check_transfer_limits(
    session: Session,
    source_account_id: uuid.UUID,
    amount_cents: int,
    max_single_limit: int = MAX_TRANSACTION_AMOUNT_CENTS,
    daily_limit: int = DAILY_TRANSFER_LIMIT_CENTS,
) -> None:
    """Enforce both per-transaction and rolling 24-hour limits."""
    if amount_cents > max_single_limit:
        raise TransactionLimitExceeded(
            f"Transaction amount ({amount_cents} cents) exceeds single limit of {max_single_limit} cents"
        )

    spent_last_24h = get_daily_transferred_amount(session, source_account_id)
    if spent_last_24h + amount_cents > daily_limit:
        remaining = max(0, daily_limit - spent_last_24h)
        raise DailyLimitExceeded(
            f"Transfer exceeds rolling 24h limit ({daily_limit} cents). Already transferred: {spent_last_24h} cents. Remaining limit: {remaining} cents"
        )
