"""add ledger_entries indexes

Revision ID: 0018_ledger_indexes
Revises: 0017_account_status_lifecycle
"""
from alembic import op

revision = "0018_ledger_indexes"
down_revision = "0017_account_status_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_ledger_entries_account_created", "ledger_entries", ["account_id", "created_at"])
    op.create_index("ix_ledger_entries_transaction_id", "ledger_entries", ["transaction_id"])


def downgrade() -> None:
    op.drop_index("ix_ledger_entries_transaction_id", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_account_created", table_name="ledger_entries")
