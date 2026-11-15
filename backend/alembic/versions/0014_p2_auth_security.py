"""p2 auth security: mfa fernet migration, replay/lockout, backup codes

Revision ID: 0014_p2_auth_security
Revises: 0013_p3_outbox_dead_state
Create Date: 2026-11-15
"""
import base64, hashlib, hmac, os
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from app.security.mfa import encrypt_mfa_secret, get_active_mfa_key_id

revision = "0014_p2_auth_security"
down_revision = "0013_p3_outbox_dead_state"
branch_labels = None
depends_on = None


def _decrypt_v1(stored: str) -> str:
    raw_key = os.getenv("FINGUARD_MFA_ENCRYPTION_KEY") or os.getenv("FINGUARD_JWT_SECRET", "dev-only-insecure-secret-key-change-me-32chars")
    key = hashlib.sha256(raw_key.encode("utf-8")).digest()
    raw = base64.urlsafe_b64decode(stored[len("enc:v1:"):].encode("ascii"))
    nonce, mac, cipher_bytes = raw[:16], raw[16:32], raw[32:]
    expected = hmac.new(key, nonce + cipher_bytes, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(mac, expected):
        raise ValueError("Cannot decrypt legacy v1 MFA secret")
    stream = hashlib.pbkdf2_hmac("sha256", key, nonce, 10_000, dklen=len(cipher_bytes))
    return bytes(a ^ b for a, b in zip(cipher_bytes, stream)).decode("utf-8")


def upgrade() -> None:
    op.alter_column("users", "mfa_secret", type_=sa.String(length=512), existing_nullable=True)
    op.add_column("users", sa.Column("mfa_last_totp_step", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("mfa_key_id", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("mfa_failed_attempts", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("mfa_locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("mfa_backup_codes", sa.JSON(), nullable=True))
    op.create_table(
        "mfa_token_states",
        sa.Column("jti", sa.String(length=64), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, mfa_secret FROM users WHERE mfa_secret IS NOT NULL")).fetchall()
    kid = get_active_mfa_key_id()
    for uid, sec in rows:
        plain = _decrypt_v1(sec) if sec.startswith("enc:v1:") else sec
        if not plain.startswith("enc:v2:"):
            conn.execute(sa.text("UPDATE users SET mfa_secret = :s, mfa_key_id = :k WHERE id = :id"), {"s": encrypt_mfa_secret(plain), "k": kid, "id": uid})


def downgrade() -> None:
    op.drop_table("mfa_token_states")
    op.drop_column("users", "mfa_backup_codes")
    op.drop_column("users", "mfa_locked_until")
    op.drop_column("users", "mfa_failed_attempts")
    op.drop_column("users", "mfa_key_id")
    op.drop_column("users", "mfa_last_totp_step")
    op.alter_column("users", "mfa_secret", type_=sa.String(length=255), existing_nullable=True)
