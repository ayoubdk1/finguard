"""add mfa columns to users

Revision ID: 0007_user_mfa_columns
Revises: 0006_refresh_token_sessions
Create Date: 2026-11-09 00:55:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_user_mfa_columns"
down_revision: Union[str, Sequence[str], None] = "0006_refresh_token_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("mfa_secret", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "mfa_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "mfa_secret")
