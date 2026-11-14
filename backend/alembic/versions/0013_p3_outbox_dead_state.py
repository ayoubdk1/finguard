"""add status, next_attempt_at, and last_error to outbox_events

Revision ID: 0013_p3_outbox_dead_state
Revises: 0012_p1_financial_correctness
Create Date: 2026-11-14 14:20:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0013_p3_outbox_dead_state"
down_revision: Union[str, None] = "0012_p1_financial_correctness"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "outbox_events",
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
    )
    op.add_column(
        "outbox_events",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "outbox_events",
        sa.Column("last_error", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("outbox_events", "last_error")
    op.drop_column("outbox_events", "next_attempt_at")
    op.drop_column("outbox_events", "status")
