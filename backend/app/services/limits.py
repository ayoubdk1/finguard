import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.currencies import CURRENCY_EXPONENTS
from app.db.models import LedgerEntry, Transaction, TransactionStatus

# Default Fintech Limits in major units (10,000 single / 50,000 daily)
MAX_TRANSACTION_MAJOR_UNITS = 10_000
DAILY_TRANSFER_MAJOR_UNITS = 50_000
MAX_TRANSACTION_AMOUNT_CENTS = 1_000_000
DAILY_TRANSFER_LIMIT_CENTS = 5_000_000


class TransactionSecurityError(Exception):
    """Base exception for transaction security violations."""


class TransactionLimitExceeded(TransactionSecurityError):
    pass


class DailyLimitExceeded(TransactionSecurityError):
    pass


def get_currency_limits(currency: str) -> tuple[int, int]:
    """Return (max_single_minor_units, daily_limit_minor_units) scaled by currency exponent."""
    exp = CURRENCY_EXPONENTS.get(currency.upper(), 2)
    scale = 10 ** exp
    return MAX_TRANSACTION_MAJOR_UNITS * scale, DAILY_TRANSFER_MAJOR_UNITS * scale


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
    *,
    currency: str = "USD",
    max_single_limit: int | None = None,
    daily_limit: int | None = None,
) -> None:
    """Enforce both per-transaction and rolling 24-hour limits scaled by currency."""
    default_single, default_daily = get_currency_limits(currency)
    eff_single = max_single_limit if max_single_limit is not None else default_single
    eff_daily = daily_limit if daily_limit is not None else default_daily

    if amount_cents > eff_single:
        raise TransactionLimitExceeded(
            f"Transaction amount ({amount_cents} minor units {currency}) exceeds single limit of {eff_single}"
        )

    spent_last_24h = get_daily_transferred_amount(session, source_account_id)
    if spent_last_24h + amount_cents > eff_daily:
        remaining = max(0, eff_daily - spent_last_24h)
        raise DailyLimitExceeded(
            f"Transfer exceeds rolling 24h limit ({eff_daily} minor units {currency}). Already transferred: {spent_last_24h}. Remaining: {remaining}"
        )
