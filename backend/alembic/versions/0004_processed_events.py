"""add processed events for idempotent Kafka consumer

Revision ID: 0004
Revises: 44b47c86ac8d
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "44b47c86ac8d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "processed_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )


def downgrade():
    op.drop_table("processed_events")
