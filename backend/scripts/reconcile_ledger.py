from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Account, LedgerEntry, Transaction, TransactionStatus
from app.db.session import SessionLocal


def verify_ledger_reconciliation(db: Session) -> dict:
    """Verify global double-entry balance (sum=0), per-currency balance, and per-tx balance."""
    global_sum = int(db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount), 0))) or 0)
    if global_sum != 0:
        raise AssertionError(f"Global ledger imbalance detected: sum={global_sum}")

    currency_rows = db.execute(
        select(LedgerEntry.currency, func.coalesce(func.sum(LedgerEntry.amount), 0))
        .group_by(LedgerEntry.currency)
    ).all()
    for currency, csum in currency_rows:
        if int(csum) != 0:
            raise AssertionError(f"Currency {currency} imbalance detected: sum={csum}")

    unbalanced_txs = db.execute(
        select(LedgerEntry.transaction_id, func.sum(LedgerEntry.amount))
        .join(Transaction, Transaction.id == LedgerEntry.transaction_id)
        .where(Transaction.status == TransactionStatus.POSTED)
        .group_by(LedgerEntry.transaction_id)
        .having(func.sum(LedgerEntry.amount) != 0)
    ).all()
    if unbalanced_txs:
        raise AssertionError(f"Unbalanced POSTED transactions found: {unbalanced_txs}")

    total_accounts = int(db.scalar(select(func.count()).select_from(Account)) or 0)
    return {"status": "reconciled", "global_sum": global_sum, "accounts_checked": total_accounts}


if __name__ == "__main__":
    with SessionLocal() as session:
        report = verify_ledger_reconciliation(session)
        print("Reconciliation OK:", report)
