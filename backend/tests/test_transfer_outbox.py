
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    AccountType,
    User,
    Transaction,
    OutboxEvent,
)
from app.db.session import engine
from app.services.ledger import (
    EntryInput,
    post_transaction,
    get_balance,
)
from app.services.outbox import enqueue_transfer_posted


def test_successful_transfer_creates_outbox_event():

    # Safety: never test against development database
    assert engine.url.database == "finguard_test"

    # Outer transaction keeps test data isolated
    with engine.connect() as connection:
        outer_transaction = connection.begin()

        try:
            with Session(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as db:

                # 1. Create test user and accounts
                user = User(
                    email=f"test-{uuid.uuid4()}@example.com",
                    full_name="Outbox Test User",
                )

                funding = Account(
                    name="TEST_FUNDING",
                    account_type=AccountType.SYSTEM,
                    currency="TND",
                )

                alice = Account(
                    user_id=None,
                    name="Alice Test",
                    account_type=AccountType.CUSTOMER,
                    currency="TND",
                )

                bob = Account(
                    user_id=None,
                    name="Bob Test",
                    account_type=AccountType.CUSTOMER,
                    currency="TND",
                )

                # 1. Create user first
                user = User(
                    email=f"test-{uuid.uuid4()}@example.com",
                    full_name="Outbox Test User",
                )

                db.add(user)
                db.flush()

                # 2. Create funding account
                funding = Account(
                    name="TEST_FUNDING",
                    account_type=AccountType.SYSTEM,
                    currency="TND",
                )

                # 3. Create CUSTOMER accounts with valid user_id
                alice = Account(
                    user_id=user.id,
                    name="Alice Test",
                    account_type=AccountType.CUSTOMER,
                    currency="TND",
                )

                bob = Account(
                    user_id=user.id,
                    name="Bob Test",
                    account_type=AccountType.CUSTOMER,
                    currency="TND",
                )

                db.add_all([funding, alice, bob])
                db.flush()


                # 2. Fund Alice with 10,000 cents
                post_transaction(
                    session=db,
                    idempotency_key=str(uuid.uuid4()),
                    entries=[
                        EntryInput(funding.id, -10000),
                        EntryInput(alice.id, 10000),
                    ],
                    description="Test funding",
                )

                # 3. Transfer 2,000 cents from Alice to Bob
                tx = post_transaction(
                    session=db,
                    idempotency_key=str(uuid.uuid4()),
                    entries=[
                        EntryInput(alice.id, -2000),
                        EntryInput(bob.id, 2000),
                    ],
                    description="Test transfer with outbox",
                    before_commit=lambda session, tx: enqueue_transfer_posted(
                        session=session,
                        transaction_id=tx.id,
                        source_account_id=alice.id,
                        destination_account_id=bob.id,
                        amount_cents=2000,
                        currency="TND",
                    ),
                )

                # 4. Find the corresponding outbox event
                events = db.scalars(
                    select(OutboxEvent).where(
                        OutboxEvent.aggregate_id == tx.id
                    )
                ).all()

                # 5. Verify exactly one event was created
                assert len(events) == 1

                event = events[0]

                assert event.event_type == "TransferPosted"
                assert event.payload["transaction_id"] == str(tx.id)
                assert event.payload["amount_cents"] == 2000
                assert event.payload["currency"] == "TND"
                assert event.published_at is None

                # 6. Verify money moved correctly
                assert get_balance(db, alice.id) == 8000
                assert get_balance(db, bob.id) == 2000

        finally:
            # Undo all test data, including internal commits
            outer_transaction.rollback()


def test_outbox_failure_rolls_back_transfer():
    # Safety: use test database only
    assert engine.url.database == "finguard_test"

    with engine.connect() as connection:
        outer_transaction = connection.begin()

        try:
            with Session(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as db:
                # 1. Create test user
                user = User(
                    email=f"rollback-{uuid.uuid4()}@example.com",
                    full_name="Rollback Test User",
                )
                db.add(user)
                db.flush()

                # 2. Create accounts
                funding = Account(
                    name="TEST_FUNDING",
                    account_type=AccountType.SYSTEM,
                    currency="TND",
                )
                alice = Account(
                    user_id=user.id,
                    name="Alice Test",
                    account_type=AccountType.CUSTOMER,
                    currency="TND",
                )
                bob = Account(
                    user_id=user.id,
                    name="Bob Test",
                    account_type=AccountType.CUSTOMER,
                    currency="TND",
                )
                db.add_all([funding, alice, bob])
                db.flush()

                # Fund Alice with 10,000 cents
                post_transaction(
                    session=db,
                    idempotency_key=str(uuid.uuid4()),
                    entries=[
                        EntryInput(funding.id, -10000),
                        EntryInput(alice.id, 10000),
                    ],
                    description="Test funding",
                )

                # 3. Transfer attempt: Alice -> Bob (2,000 cents) with simulated failure
                transfer_key = str(uuid.uuid4())
                failed_tx_id = None

                def failing_callback(session, tx):
                    nonlocal failed_tx_id
                    failed_tx_id = tx.id
                    enqueue_transfer_posted(
                        session=session,
                        transaction_id=tx.id,
                        source_account_id=alice.id,
                        destination_account_id=bob.id,
                        amount_cents=2000,
                        currency="TND",
                    )
                    raise RuntimeError("Simulated failure")

                with pytest.raises(RuntimeError):
                    post_transaction(
                        session=db,
                        idempotency_key=transfer_key,
                        entries=[
                            EntryInput(alice.id, -2000),
                            EntryInput(bob.id, 2000),
                        ],
                        description="Test transfer failure",
                        before_commit=failing_callback,
                    )

                # Expected balances after the failure:
                # - Alice: 10,000 cents
                # - Bob: 0 cents
                assert get_balance(db, alice.id) == 10000
                assert get_balance(db, bob.id) == 0

                # - Failed transaction: Not found
                failed_tx = db.scalars(
                    select(Transaction).where(
                        Transaction.idempotency_key == transfer_key
                    )
                ).first()
                assert failed_tx is None

                # - Failed outbox event: Not found
                failed_event = db.scalars(
                    select(OutboxEvent).where(
                        OutboxEvent.aggregate_id == failed_tx_id
                    )
                ).first()
                assert failed_event is None

        finally:
            outer_transaction.rollback()
