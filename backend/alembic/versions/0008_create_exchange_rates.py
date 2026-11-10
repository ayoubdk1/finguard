"""create exchange_rates table and seed initial rates

Revision ID: 0008_create_exchange_rates
Revises: 0007_user_mfa_columns
Create Date: 2026-11-10 20:15:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008_create_exchange_rates"
down_revision: Union[str, Sequence[str], None] = "0007_user_mfa_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create table
    op.create_table(
        "exchange_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("target_currency", sa.String(length=3), nullable=False),
        sa.Column("rate", sa.BigInteger(), nullable=False),
        sa.Column("fee_bps", sa.Integer(), server_default="50", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_exchange_rates_pair",
        "exchange_rates",
        ["base_currency", "target_currency"],
    )

    # 2. Seed initial FX rates
    op.execute(
        """
        INSERT INTO exchange_rates (id, base_currency, target_currency, rate, fee_bps) VALUES
        (gen_random_uuid(), 'USD', 'EUR', 920000, 50),
        (gen_random_uuid(), 'EUR', 'USD', 1086956, 50),
        (gen_random_uuid(), 'USD', 'TND', 3100000, 50),
        (gen_random_uuid(), 'TND', 'USD', 322580, 50),
        (gen_random_uuid(), 'EUR', 'TND', 3360000, 50),
        (gen_random_uuid(), 'TND', 'EUR', 297619, 50);
        """
    )

    # 3. Ensure SYSTEM_FX clearing accounts exist for TND, USD, EUR
    op.execute(
        """
        INSERT INTO accounts (id, user_id, name, account_type, currency, created_at)
        SELECT gen_random_uuid(), NULL, 'SYSTEM_FX', 'SYSTEM', c, NOW()
        FROM (VALUES ('TND'), ('USD'), ('EUR')) AS currencies(c)
        WHERE NOT EXISTS (
            SELECT 1 FROM accounts WHERE name = 'SYSTEM_FX' AND currency = c
        );
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM accounts WHERE name = 'SYSTEM_FX';")
    op.drop_index("ix_exchange_rates_pair", table_name="exchange_rates")
    op.drop_table("exchange_rates")
