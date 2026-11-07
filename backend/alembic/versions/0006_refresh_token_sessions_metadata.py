"""add session metadata columns to refresh_tokens

Revision ID: 0006_refresh_token_sessions
Revises: 0005_refresh_tokens_rbac
Create Date: 2026-11-07 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_refresh_token_sessions"
down_revision: Union[str, Sequence[str], None] = "0005_refresh_tokens_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column("user_agent", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("ip_address", sa.String(length=45), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("refresh_tokens", "ip_address")
    op.drop_column("refresh_tokens", "user_agent")