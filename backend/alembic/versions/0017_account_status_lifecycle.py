"""add account status lifecycle

Revision ID: 0017_account_status_lifecycle
Revises: 0016_p4_audit_compliance
"""
import sqlalchemy as sa
from alembic import op

revision = "0017_account_status_lifecycle"
down_revision = "0016_p4_audit_compliance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"))
    op.create_check_constraint("ck_accounts_status", "accounts", "status IN ('ACTIVE', 'FROZEN', 'CLOSED')")


def downgrade() -> None:
    op.drop_constraint("ck_accounts_status", "accounts", type_="check")
    op.drop_column("accounts", "status")
