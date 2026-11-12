"""widen users.mfa_secret to 255 for encrypted secrets

Revision ID: 0011_widen_mfa_secret
Revises: 0010_user_status_login_history
Create Date: 2026-11-12 22:18:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0011_widen_mfa_secret"
down_revision: Union[str, None] = "0010_user_status_login_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "mfa_secret", type_=sa.String(length=255), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("users", "mfa_secret", type_=sa.String(length=64), existing_nullable=True)
