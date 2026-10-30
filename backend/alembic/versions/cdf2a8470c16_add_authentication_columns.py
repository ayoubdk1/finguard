"""add authentication columns

Revision ID: cdf2a8470c16
Revises: 4bcf9327ff29
Create Date: 2026-10-29 19:05:54.702542

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cdf2a8470c16'
down_revision: Union[str, Sequence[str], None] = '4bcf9327ff29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add password hash
    op.add_column(
        "users",
        sa.Column(
            "password_hash",
            sa.String(length=255),
            nullable=True,
        ),
    )
    # Add customer/admin role
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default="CUSTOMER",
        ),
    )
    # Restrict allowed role values
    op.create_check_constraint(
        "ck_users_role_allowed",
        "users",
        "role IN ('CUSTOMER', 'ADMIN')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_users_role_allowed",
        "users",
        type_="check",
    )
    op.drop_column("users", "role")
    op.drop_column("users", "password_hash")
