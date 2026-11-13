"""add scoped idempotency, request_hash, and original_transaction_id on transactions

Revision ID: 0012_p1_financial_correctness
Revises: 0011_widen_mfa_secret
Create Date: 2026-11-13 21:30:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0012_p1_financial_correctness"
down_revision: Union[str, None] = "0011_widen_mfa_secret"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("idempotency_scope", sa.String(length=120), nullable=False, server_default="global"),
    )
    op.add_column(
        "transactions",
        sa.Column("request_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column(
            "original_transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id"),
            nullable=True,
        ),
    )
    op.create_unique_constraint("uq_transactions_original_tx_id", "transactions", ["original_transaction_id"])
    op.execute("ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_idempotency_key_key")
    op.create_unique_constraint(
        "uq_transactions_scope_key",
        "transactions",
        ["idempotency_scope", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_transactions_scope_key", "transactions", type_="unique")
    op.create_unique_constraint("transactions_idempotency_key_key", "transactions", ["idempotency_key"])
    op.drop_constraint("uq_transactions_original_tx_id", "transactions", type_="unique")
    op.drop_column("transactions", "original_transaction_id")
    op.drop_column("transactions", "request_hash")
    op.drop_column("transactions", "idempotency_scope")
