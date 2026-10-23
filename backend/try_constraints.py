import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

engine = create_engine("postgresql+psycopg://finguard:finguard@localhost:5432/finguard")


def attempt(label, fn):
    try:
        with engine.begin() as conn:
            fn(conn)
        print(f"ALLOWED   {label}")
    except DBAPIError as e:
        print(f"REJECTED  {label} -> {str(e.orig).splitlines()[0]}")


user_id, sys_id, cust_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

with engine.begin() as conn:
    conn.execute(
        text("INSERT INTO users (id, email, full_name) VALUES (:id, :email, 'Test User')"),
        {"id": user_id, "email": f"{user_id}@test.local"},
    )
    conn.execute(
        text(
            "INSERT INTO accounts (id, user_id, name, account_type, currency) VALUES "
            "(:sid, NULL, 'SYSTEM_FUNDING', CAST('SYSTEM' AS account_type), 'USD'), "
            "(:cid, :uid, 'Alice', CAST('CUSTOMER' AS account_type), 'USD')"
        ),
        {"sid": sys_id, "cid": cust_id, "uid": user_id},
    )


def new_tx(conn):
    tx_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO transactions (id, idempotency_key, description, status) "
            "VALUES (:id, :key, 'test', CAST('POSTED' AS transaction_status))"
        ),
        {"id": tx_id, "key": str(tx_id)},
    )
    return tx_id


def entry(conn, tx_id, account_id, amount, currency="USD"):
    conn.execute(
        text(
            "INSERT INTO ledger_entries (transaction_id, account_id, amount, currency) "
            "VALUES (:t, :a, :amt, :cur)"
        ),
        {"t": tx_id, "a": account_id, "amt": amount, "cur": currency},
    )


def valid_deposit(conn):
    tx = new_tx(conn)
    entry(conn, tx, sys_id, -5000)
    entry(conn, tx, cust_id, 5000)


def zero_amount(conn):
    tx = new_tx(conn)
    entry(conn, tx, cust_id, 0)
    entry(conn, tx, sys_id, 0)


def unbalanced(conn):
    tx = new_tx(conn)
    entry(conn, tx, sys_id, -100)
    entry(conn, tx, cust_id, 50)


def single_entry(conn):
    tx = new_tx(conn)
    entry(conn, tx, sys_id, 0 + 1)


def wrong_currency(conn):
    tx = new_tx(conn)
    entry(conn, tx, sys_id, -100, "EUR")
    entry(conn, tx, cust_id, 100, "EUR")


def overdraft(conn):
    tx = new_tx(conn)
    entry(conn, tx, cust_id, -6000)
    entry(conn, tx, sys_id, 6000)


def update_entry(conn):
    conn.execute(text("UPDATE ledger_entries SET amount = 1 WHERE account_id = :a"), {"a": cust_id})


def delete_entry(conn):
    conn.execute(text("DELETE FROM ledger_entries WHERE account_id = :a"), {"a": cust_id})


attempt("valid deposit of 5000", valid_deposit)
attempt("zero amount", zero_amount)
attempt("unbalanced transaction", unbalanced)
attempt("transaction with 1 entry", single_entry)
attempt("entry currency differs from account currency", wrong_currency)
attempt("overdraft of a customer account", overdraft)
attempt("update a ledger entry", update_entry)
attempt("delete a ledger entry", delete_entry)