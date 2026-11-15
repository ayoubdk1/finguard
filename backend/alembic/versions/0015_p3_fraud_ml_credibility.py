"""p3 fraud and ml credibility: jsonb reasons, sla, transfer_attempts

Revision ID: 0015_p3_fraud_ml_credibility
Revises: 0014_p2_auth_security
Create Date: 2026-11-15
"""
import json
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_p3_fraud_ml_credibility"
down_revision = "0014_p2_auth_security"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fraud_alerts", sa.Column("reasons_json", postgresql.JSONB(), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, reasons FROM fraud_alerts")).fetchall()
    for aid, raw_r in rows:
        parsed: list[str]
        if isinstance(raw_r, list):
            parsed = [str(x) for x in raw_r]
        elif isinstance(raw_r, str) and raw_r.strip().startswith("["):
            try:
                parsed = [str(x) for x in json.loads(raw_r)]
            except Exception:
                parsed = [raw_r] if raw_r else []
        elif isinstance(raw_r, str) and raw_r.strip():
            parsed = [x.strip() for x in raw_r.split(",") if x.strip()]
        else:
            parsed = []
        conn.execute(sa.text("UPDATE fraud_alerts SET reasons_json = CAST(:r AS jsonb) WHERE id = :id"), {"r": json.dumps(parsed), "id": aid})

    op.drop_column("fraud_alerts", "reasons")
    op.alter_column("fraud_alerts", "reasons_json", new_column_name="reasons", nullable=False, server_default=sa.text("'[]'::jsonb"))
    op.add_column("fraud_alerts", sa.Column("assigned_to", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("fraud_alerts", sa.Column("investigated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("fraud_alerts", sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "transfer_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("destination_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table("transfer_attempts")
    op.drop_column("fraud_alerts", "sla_due_at")
    op.drop_column("fraud_alerts", "investigated_at")
    op.drop_column("fraud_alerts", "assigned_to")
    op.add_column("fraud_alerts", sa.Column("reasons_str", sa.String(length=500), nullable=False, server_default=""))
    op.drop_column("fraud_alerts", "reasons")
    op.alter_column("fraud_alerts", "reasons_str", new_column_name="reasons")
