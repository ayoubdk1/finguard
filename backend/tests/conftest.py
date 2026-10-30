
import os
import uuid
from fastapi.testclient import TestClient
from app import main as api_module

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

# Safety: tests must use finguard_test
database_url = os.getenv("DATABASE_URL")

if not database_url or make_url(database_url).database != "finguard_test":
    raise RuntimeError(
        "Tests blocked: DATABASE_URL must point to finguard_test"
    )

from app.db.models import Account, AccountType, User
from app.db.session import engine

# Double-check the actual database connection
if engine.url.database != "finguard_test":
    raise RuntimeError("Tests blocked: wrong database")


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

    try:
        yield s
    finally:
        s.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def world(session):
    """A funding account plus two customer accounts, all in USD."""

    run = uuid.uuid4().hex[:8]

    ua = User(
        email=f"alice-{run}@test.local",
        full_name="Alice"
    )

    ub = User(
        email=f"bob-{run}@test.local",
        full_name="Bob"
    )

    session.add_all([ua, ub])
    session.flush()

    funding = Account(
        name="SYSTEM_FUNDING",
        account_type=AccountType.SYSTEM,
        currency="USD"
    )

    alice = Account(
        user_id=ua.id,
        name="Alice",
        account_type=AccountType.CUSTOMER,
        currency="USD"
    )

    bob = Account(
        user_id=ub.id,
        name="Bob",
        account_type=AccountType.CUSTOMER,
        currency="USD"
    )

    session.add_all([funding, alice, bob])
    session.commit()

    return {
        "funding": funding,
        "alice": alice,
        "bob": bob
    }

@pytest.fixture
def client(session, monkeypatch):
    connection = session.connection()

    def test_session_factory():
        return Session(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )

    monkeypatch.setattr(
        api_module,
        "SessionLocal",
        test_session_factory
    )

    with TestClient(api_module.app) as test_client:
        yield test_client


from uuid import uuid4  # noqa: E402
from app.main import app  # noqa: E402
from app.security.dependencies import get_current_user  # noqa: E402


def _default_test_admin() -> User:
    return User(
        id=uuid4(),
        email="test-admin@finguard.local",
        full_name="Test Admin",
        role="ADMIN",
    )


app.dependency_overrides[get_current_user] = _default_test_admin


from app.security.rate_limit import reset_login_rate_limits  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Each test starts with a clean login rate-limit counter."""
    reset_login_rate_limits()
    yield
    reset_login_rate_limits()
