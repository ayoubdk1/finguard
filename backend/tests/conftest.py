import uuid

import pytest
from sqlalchemy.orm import Session

from app.db.models import Account, AccountType, User
from app.db.session import engine


@pytest.fixture
def session():
    """A session whose work is rolled back after each test."""
    connection = engine.connect()
    outer = connection.begin()
    s = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    yield s
    s.close()
    outer.rollback()
    connection.close()


@pytest.fixture
def world(session):
    """A funding account plus two customer accounts, all in USD."""
    run = uuid.uuid4().hex[:8]
    ua = User(email=f"alice-{run}@test.local", full_name="Alice")
    ub = User(email=f"bob-{run}@test.local", full_name="Bob")
    session.add_all([ua, ub])
    session.flush()
    funding = Account(name="SYSTEM_FUNDING", account_type=AccountType.SYSTEM, currency="USD")
    alice = Account(user_id=ua.id, name="Alice", account_type=AccountType.CUSTOMER, currency="USD")
    bob = Account(user_id=ub.id, name="Bob", account_type=AccountType.CUSTOMER, currency="USD")
    session.add_all([funding, alice, bob])
    session.commit()
    return {"funding": funding, "alice": alice, "bob": bob}
