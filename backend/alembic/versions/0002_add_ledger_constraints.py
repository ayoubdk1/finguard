"""add ledger constraints

Revision ID: 0002
Revises: e27c5f8ece90
"""
from alembic import op

revision = "0002"
down_revision = "e27c5f8ece90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- CHECK constraints (R2, R3, S1) ---
    op.create_check_constraint(
        "ck_ledger_entries_amount_nonzero", "ledger_entries", "amount <> 0"
    )
    op.create_check_constraint(
        "ck_ledger_entries_currency_format", "ledger_entries", "currency ~ '^[A-Z]{3}$'"
    )
    op.create_check_constraint(
        "ck_accounts_currency_format", "accounts", "currency ~ '^[A-Z]{3}$'"
    )
    op.create_check_constraint(
        "ck_accounts_user_matches_type",
        "accounts",
        "(account_type = 'SYSTEM' AND user_id IS NULL) "
        "OR (account_type = 'CUSTOMER' AND user_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_transactions_idempotency_key_not_empty",
        "transactions",
        "length(idempotency_key) > 0",
    )

    # --- Entry currency must match its account's currency (I2) ---
    op.create_unique_constraint("uq_accounts_id_currency", "accounts", ["id", "currency"])
    op.create_foreign_key(
        "fk_ledger_entries_account_currency",
        "ledger_entries",
        "accounts",
        ["account_id", "currency"],
        ["id", "currency"],
    )

    # --- Immutability (I3) ---
    op.execute(
        """
        CREATE FUNCTION ledger_entries_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'ledger_entries is append-only (rule I3)';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ledger_entries_immutable
        BEFORE UPDATE OR DELETE ON ledger_entries
        FOR EACH ROW EXECUTE FUNCTION ledger_entries_immutable();
        """
    )

    # --- Balanced transactions, at least 2 entries, one currency (I1, I2, I9) ---
    op.execute(
        """
        CREATE FUNCTION ledger_check_transaction() RETURNS trigger AS $$
        DECLARE
            entry_count integer;
            total bigint;
            currency_count integer;
        BEGIN
            SELECT count(*), COALESCE(sum(amount), 0), count(DISTINCT currency)
              INTO entry_count, total, currency_count
              FROM ledger_entries
             WHERE transaction_id = NEW.transaction_id;

            IF entry_count < 2 THEN
                RAISE EXCEPTION 'transaction needs at least 2 entries (rule I9)';
            END IF;
            IF total <> 0 THEN
                RAISE EXCEPTION 'transaction is not balanced (rule I1)';
            END IF;
            IF currency_count <> 1 THEN
                RAISE EXCEPTION 'transaction mixes currencies (rule I2)';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_ledger_transaction_balanced
        AFTER INSERT ON ledger_entries
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION ledger_check_transaction();
        """
    )

    # --- No overdraft on customer accounts (I5) ---
    op.execute(
        """
        CREATE FUNCTION ledger_check_overdraft() RETURNS trigger AS $$
        DECLARE
            acct_type account_type;
            bal bigint;
        BEGIN
            SELECT account_type INTO acct_type FROM accounts WHERE id = NEW.account_id;
            IF acct_type = 'CUSTOMER' THEN
                SELECT COALESCE(sum(amount), 0) INTO bal
                  FROM ledger_entries
                 WHERE account_id = NEW.account_id;
                IF bal < 0 THEN
                    RAISE EXCEPTION 'insufficient funds (rule I5)';
                END IF;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_ledger_no_overdraft
        AFTER INSERT ON ledger_entries
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION ledger_check_overdraft();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_ledger_no_overdraft ON ledger_entries")
    op.execute("DROP FUNCTION IF EXISTS ledger_check_overdraft()")
    op.execute("DROP TRIGGER IF EXISTS trg_ledger_transaction_balanced ON ledger_entries")
    op.execute("DROP FUNCTION IF EXISTS ledger_check_transaction()")
    op.execute("DROP TRIGGER IF EXISTS trg_ledger_entries_immutable ON ledger_entries")
    op.execute("DROP FUNCTION IF EXISTS ledger_entries_immutable()")
    op.drop_constraint("fk_ledger_entries_account_currency", "ledger_entries", type_="foreignkey")
    op.drop_constraint("uq_accounts_id_currency", "accounts", type_="unique")
    op.drop_constraint("ck_transactions_idempotency_key_not_empty", "transactions", type_="check")
    op.drop_constraint("ck_accounts_user_matches_type", "accounts", type_="check")
    op.drop_constraint("ck_accounts_currency_format", "accounts", type_="check")
    op.drop_constraint("ck_ledger_entries_currency_format", "ledger_entries", type_="check")
    op.drop_constraint("ck_ledger_entries_amount_nonzero", "ledger_entries", type_="check")