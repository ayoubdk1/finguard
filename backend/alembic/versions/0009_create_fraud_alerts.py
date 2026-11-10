"""create fraud_alerts table

Revision ID: 0009_create_fraud_alerts
Revises: 0008_create_exchange_rates
Create Date: 2026-11-10 20:50:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009_create_fraud_alerts"
down_revision: Union[str, Sequence[str], None] = "0008_create_exchange_rates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create table using String or checkfirst enum
    op.create_table(
        "fraud_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("risk_score", sa.BigInteger(), nullable=False),
        sa.Column("reasons", sa.String(length=500), server_default="", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("analyst_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("analyst_notes", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_fraud_alerts_status", "fraud_alerts", ["status"])
    op.create_index("ix_fraud_alerts_account_id", "fraud_alerts", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_fraud_alerts_account_id", table_name="fraud_alerts")
    op.drop_index("ix_fraud_alerts_status", table_name="fraud_alerts")
    op.drop_table("fraud_alerts")
