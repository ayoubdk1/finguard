"""Unit/integration tests that do not require a running Redpanda broker."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import OutboxEvent, ProcessedEvent
from app.db.session import engine
from app.services.event_streaming import (
    make_envelope, publish_batch, record_processed_event, validate_transfer_event,
)


class FakeProducer:
    def __init__(self, fail=False):
        self.fail = fail
        self.messages = []
        self.callback = None

    def produce(self, *, topic, key, value, on_delivery):
        self.messages.append((topic, key, value))
        self.callback = on_delivery

    def flush(self, timeout):
        self.callback(RuntimeError("simulated broker failure") if self.fail else None, None)
        return 0


def _create_event(session):
    event = OutboxEvent(
        id=uuid.uuid4(),
        aggregate_id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
        event_type="TransferPosted",
        event_version=1,
        payload={
            "transaction_id": str(uuid.uuid4()),
            "source_account_id": str(uuid.uuid4()),
            "destination_account_id": str(uuid.uuid4()),
            "amount_cents": 2000,
            "currency": "TND",
        },
        publish_attempts=0,
    )
    session.add(event)
    session.flush()
    return event.id


def test_publisher_retries_and_marks_success():
    assert engine.url.database == "finguard_test"
    with engine.connect() as conn:
        outer = conn.begin()
        factory = lambda: Session(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        try:
            with factory() as db:
                with db.begin():
                    event_id = _create_event(db)

            failing = FakeProducer(fail=True)
            assert publish_batch(failing, session_factory=factory) == 0
            with factory() as db:
                e = db.get(OutboxEvent, event_id)
                assert e.published_at is None
                assert e.publish_attempts == 1

            successful = FakeProducer()
            assert publish_batch(successful, session_factory=factory) == 1
            assert len(successful.messages) == 1
            with factory() as db:
                e = db.get(OutboxEvent, event_id)
                assert e.published_at is not None
                assert e.publish_attempts == 2
            assert publish_batch(successful, session_factory=factory) == 0
        finally:
            if outer.is_active:
                outer.rollback()


def test_consumer_rejects_duplicate_event():
    assert engine.url.database == "finguard_test"
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            with Session(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint") as db:
                with db.begin():
                    event_id = _create_event(db)
                    event = db.get(OutboxEvent, event_id)
                    envelope = make_envelope(event)
                    assert validate_transfer_event(envelope) == event_id
                    assert record_processed_event(db, envelope) is True
                with db.begin():
                    assert record_processed_event(db, envelope) is False
                assert db.get(ProcessedEvent, event_id) is not None
        finally:
            if outer.is_active:
                outer.rollback()
