import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db.models import Account, AccountType, Transaction
from app.services.ledger import (
    AccountNotFound,
    EntryInput,
    InsufficientFunds,
    InvalidTransaction,
    get_balance,
    post_transaction,
)


def key() -> str:
    return uuid.uuid4().hex


def deposit(session, w, amount, k=None):
    return post_transaction(
        session,
        k or key(),
        [EntryInput(w["funding"].id, -amount), EntryInput(w["alice"].id, amount)],
        "deposit",
    )


# ---------- Service-level rules ----------

def test_deposit_updates_balances(session, world):
    deposit(session, world, 5000)
    assert get_balance(session, world["alice"].id) == 5000
    assert get_balance(session, world["funding"].id) == -5000


def test_transfer_moves_money(session, world):
    deposit(session, world, 5000)
    post_transaction(
        session, key(),
        [EntryInput(world["alice"].id, -1250), EntryInput(world["bob"].id, 1250)],
    )
    assert get_balance(session, world["alice"].id) == 3750
    assert get_balance(session, world["bob"].id) == 1250


def test_i1_unbalanced_rejected(session, world):
    with pytest.raises(InvalidTransaction):
        post_transaction(
            session, key(),
            [EntryInput(world["funding"].id, -100), EntryInput(world["alice"].id, 50)],
        )


def test_r3_zero_amount_rejected(session, world):
    with pytest.raises(InvalidTransaction):
        post_transaction(
            session, key(),
            [EntryInput(world["alice"].id, 0), EntryInput(world["bob"].id, 0)],
        )


def test_r1_float_amount_rejected(session, world):
    with pytest.raises(InvalidTransaction):
        post_transaction(
            session, key(),
            [EntryInput(world["funding"].id, -10.5), EntryInput(world["alice"].id, 10.5)],
        )


def test_i9_single_entry_rejected(session, world):
    with pytest.raises(InvalidTransaction):
        post_transaction(session, key(), [EntryInput(world["alice"].id, 100)])


def test_i5_overdraft_rejected_and_balance_unchanged(session, world):
    deposit(session, world, 1000)
    with pytest.raises(InsufficientFunds):
        post_transaction(
            session, key(),
            [EntryInput(world["alice"].id, -1001), EntryInput(world["bob"].id, 1001)],
        )
    assert get_balance(session, world["alice"].id) == 1000
    assert get_balance(session, world["bob"].id) == 0


def test_spending_exact_balance_is_allowed(session, world):
    deposit(session, world, 1000)
    post_transaction(
        session, key(),
        [EntryInput(world["alice"].id, -1000), EntryInput(world["bob"].id, 1000)],
    )
    assert get_balance(session, world["alice"].id) == 0


def test_system_account_may_go_negative(session, world):
    deposit(session, world, 5000)
    assert get_balance(session, world["funding"].id) == -5000


def test_i7_idempotent_replay_creates_one_transaction(session, world):
    k = key()
    first = deposit(session, world, 5000, k)
    second = deposit(session, world, 5000, k)
    assert first.id == second.id
    assert get_balance(session, world["alice"].id) == 5000
    found = session.scalars(
        select(Transaction.id).where(Transaction.idempotency_key == k)
    ).all()
    assert len(found) == 1


def test_unknown_account_rejected(session, world):
    with pytest.raises(AccountNotFound):
        post_transaction(
            session, key(),
            [EntryInput(uuid.uuid4(), -100), EntryInput(world["alice"].id, 100)],
        )


def test_i2_mixed_currency_rejected(session, world):
    eur = Account(
        user_id=world["alice"].user_id, name="Alice EUR",
        account_type=AccountType.CUSTOMER, currency="EUR",
    )
    session.add(eur)
    session.commit()
    with pytest.raises(InvalidTransaction):
        post_transaction(
            session, key(),
            [EntryInput(world["funding"].id, -100), EntryInput(eur.id, 100)],
        )


def test_i4_every_transaction_sums_to_zero(session, world):
    deposit(session, world, 5000)
    post_transaction(
        session, key(),
        [EntryInput(world["alice"].id, -700), EntryInput(world["bob"].id, 700)],
    )
    total = session.scalar(text("SELECT COALESCE(SUM(amount), 0) FROM ledger_entries"))
    assert total == 0


# ---------- Database-level rules (bypass the service) ----------

def _raw_tx(session):
    tx_id = uuid.uuid4()
    session.execute(
        text(
            "INSERT INTO transactions (id, idempotency_key, description, status) "
            "VALUES (:id, :k, 'raw', CAST('POSTED' AS transaction_status))"
        ),
        {"id": tx_id, "k": str(tx_id)},
    )
    return tx_id


def _raw_entry(session, tx_id, account_id, amount, currency="USD"):
    session.execute(
        text(
            "INSERT INTO ledger_entries (transaction_id, account_id, amount, currency) "
            "VALUES (:t, :a, :amt, :c)"
        ),
        {"t": tx_id, "a": account_id, "amt": amount, "c": currency},
    )


def test_db_rejects_zero_amount(session, world):
    tx = _raw_tx(session)
    with pytest.raises(DBAPIError):
        _raw_entry(session, tx, world["alice"].id, 0)


def test_db_rejects_wrong_entry_currency(session, world):
    tx = _raw_tx(session)
    with pytest.raises(DBAPIError):
        _raw_entry(session, tx, world["alice"].id, 100, "EUR")


def test_db_rejects_update_of_entry(session, world):
    deposit(session, world, 5000)
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(text("UPDATE ledger_entries SET amount = 1"))


def test_db_rejects_delete_of_entry(session, world):
    deposit(session, world, 5000)
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(text("DELETE FROM ledger_entries"))


def test_db_rejects_unbalanced_transaction_at_commit(session, world):
    tx = _raw_tx(session)
    _raw_entry(session, tx, world["funding"].id, -100)
    _raw_entry(session, tx, world["alice"].id, 50)
    with pytest.raises(DBAPIError, match="not balanced"):
        session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


def test_db_rejects_single_entry_transaction(session, world):
    tx = _raw_tx(session)
    _raw_entry(session, tx, world["alice"].id, 100)
    with pytest.raises(DBAPIError, match="at least 2 entries"):
        session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


def test_db_rejects_overdraft(session, world):
    tx = _raw_tx(session)
    _raw_entry(session, tx, world["alice"].id, -100)
    _raw_entry(session, tx, world["funding"].id, 100)
    with pytest.raises(DBAPIError, match="insufficient funds"):
        session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


def test_db_rejects_invalid_account_shape(session, world):
    with pytest.raises(DBAPIError):
        session.execute(
            text(
                "INSERT INTO accounts (id, user_id, name, account_type, currency) "
                "VALUES (gen_random_uuid(), NULL, 'bad', CAST('CUSTOMER' AS account_type), 'USD')"
            )
        )
