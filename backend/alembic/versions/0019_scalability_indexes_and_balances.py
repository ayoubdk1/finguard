"""add account_balances projection and concurrent scalability indexes

Revision ID: 0019_scalability_indexes
Revises: 0018_ledger_indexes
Create Date: 2026-11-25 21:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019_scalability_indexes"
down_revision = "0018_ledger_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_balances",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("balance", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_entry_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        """
        INSERT INTO account_balances (account_id, balance, last_entry_id, updated_at)
        SELECT a.id, COALESCE(SUM(le.amount), 0), NULL, NOW()
        FROM accounts a
        LEFT JOIN ledger_entries le ON le.account_id = a.id
        WHERE a.account_type = 'CUSTOMER'
        GROUP BY a.id
        ON CONFLICT (account_id) DO NOTHING
        """
    )

    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ledger_entries_account_id_inc_amount "
            "ON ledger_entries (account_id, id) INCLUDE (amount)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_transactions_created_at "
            "ON transactions (created_at)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_accounts_user_id "
            "ON accounts (user_id)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fraud_alerts_status_created "
            "ON fraud_alerts (status, created_at)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_outbox_events_pending_poll "
            "ON outbox_events (next_attempt_at, created_at) "
            "WHERE published_at IS NULL AND status IN ('PENDING', 'FAILED')"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_outbox_events_pending_poll")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_fraud_alerts_status_created")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_accounts_user_id")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_transactions_created_at")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_ledger_entries_account_id_inc_amount")
    op.drop_table("account_balances")
