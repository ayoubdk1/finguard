"""add audit_log hash chain columns and transactions immutability trigger

Revision ID: 0020_audit_chain_tx_immutable
Revises: 0019_scalability_indexes
Create Date: 2026-11-26 21:35:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020_audit_chain_tx_immutable"
down_revision = "0019_scalability_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_log", sa.Column("actor_role", sa.String(length=32), nullable=True))
    op.add_column("audit_log", sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("audit_log", sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("audit_log", sa.Column("prev_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_log", sa.Column("hash", sa.String(length=64), nullable=True))

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_transaction_immutable_field_update()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.status IS DISTINCT FROM OLD.status OR NEW.description IS DISTINCT FROM OLD.description THEN
                RAISE EXCEPTION 'transactions status and description are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_transactions_immutable_fields ON transactions;
        CREATE TRIGGER trg_transactions_immutable_fields
        BEFORE UPDATE ON transactions
        FOR EACH ROW
        EXECUTE FUNCTION prevent_transaction_immutable_field_update();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_transactions_immutable_fields ON transactions;")
    op.execute("DROP FUNCTION IF EXISTS prevent_transaction_immutable_field_update();")
    op.drop_column("audit_log", "hash")
    op.drop_column("audit_log", "prev_hash")
    op.drop_column("audit_log", "after")
    op.drop_column("audit_log", "before")
    op.drop_column("audit_log", "actor_role")
