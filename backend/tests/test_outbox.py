
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import OutboxEvent
from app.db.session import engine


def test_create_outbox_event():

    # Safety: only use the test database
    assert engine.url.database == "finguard_test"

    transaction_id = uuid.uuid4()

    payload = {
        "transaction_id": str(transaction_id),
        "amount_cents": 2000,
        "currency": "TND",
    }

    event = OutboxEvent(
        aggregate_id=transaction_id,
        correlation_id=uuid.uuid4(),
        event_type="TransferPosted",
        event_version=1,
        payload=payload,
    )

    with Session(engine) as session:
        try:
            # Insert the event into PostgreSQL
            session.add(event)
            session.flush()

            # Read the stored values directly from PostgreSQL
            result = session.execute(
                select(
                    OutboxEvent.payload,
                    OutboxEvent.event_type,
                    OutboxEvent.published_at,
                    OutboxEvent.publish_attempts,
                ).where(OutboxEvent.id == event.id)
            ).one()

            assert result.payload == payload
            assert result.event_type == "TransferPosted"
            assert result.published_at is None
            assert result.publish_attempts == 0

        finally:
            # Keep test data out of the database
            session.rollback()
