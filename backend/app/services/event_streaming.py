"""Redpanda integration for FinGuard's transactional outbox (simulation only)."""

import json
import os
import uuid
from datetime import datetime, timezone

from confluent_kafka import Producer
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import OutboxEvent, ProcessedEvent
from app.db.session import SessionLocal

TOPIC = "finguard.transfers.posted.v1"
DLQ_TOPIC = "finguard.transfers.posted.dlq.v1"
BROKER = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:19092")


def new_producer():
    return Producer({
        "bootstrap.servers": BROKER,
        "enable.idempotence": True,
        "acks": "all",
        "message.timeout.ms": 15000,
    })


def send_json(producer, topic: str, key: str, body: dict) -> None:
    """Return only after broker delivery acknowledgement; raise on failed delivery."""
    reports = []
    producer.produce(
        topic=topic,
        key=key.encode("utf-8"),
        value=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        on_delivery=lambda err, msg: reports.append(err),
    )
    remaining = producer.flush(20)
    if remaining != 0 or not reports or reports[-1] is not None:
        raise RuntimeError(f"Kafka delivery failed: remaining={remaining}, reports={reports}")


def make_envelope(event: OutboxEvent) -> dict:
    created = event.created_at or datetime.now(timezone.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "event_version": event.event_version,
        "occurred_at": created.astimezone(timezone.utc).isoformat(),
        "correlation_id": str(event.correlation_id),
        "payload": event.payload,
    }


def publish_batch(producer, session_factory=SessionLocal, batch_size: int = 10) -> int:
    """Publish up to batch_size events; retry pending records in a later call.

    Holds a row lock until delivery is acknowledged (simple local-dev design).
    The broker and DB cannot commit atomically: duplicate delivery is possible.
    """
    published = 0
    for _ in range(batch_size):
        failure = None
        with session_factory() as db:
            with db.begin():
                event = db.scalar(
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.published_at.is_(None),
                        OutboxEvent.event_type == "TransferPosted",
                    )
                    .order_by(OutboxEvent.created_at, OutboxEvent.id)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                if event is None:
                    return published

                event.publish_attempts += 1
                try:
                    send_json(producer, TOPIC, str(event.aggregate_id), make_envelope(event))
                except Exception as exc:
                    # Commit the attempt counter, but leave published_at NULL.
                    failure = exc
                else:
                    event.published_at = datetime.now(timezone.utc)
                    published += 1

        if failure is not None:
            print(f"Publish failed; will retry later: {failure}")
            break
    return published


def validate_transfer_event(envelope: dict) -> uuid.UUID:
    """Validate the v1 public event contract, returning its unique event ID."""
    if not isinstance(envelope, dict):
        raise ValueError("Event must be a JSON object")
    if envelope.get("event_type") != "TransferPosted" or envelope.get("event_version") != 1:
        raise ValueError("Unsupported event type/version")
    try:
        event_id = uuid.UUID(str(envelope["event_id"]))
        uuid.UUID(str(envelope["correlation_id"]))
        payload = envelope["payload"]
        uuid.UUID(str(payload["transaction_id"]))
        source = uuid.UUID(str(payload["source_account_id"]))
        destination = uuid.UUID(str(payload["destination_account_id"]))
        amount = payload["amount_cents"]
        currency = payload["currency"]
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError(f"Invalid transfer event structure: {exc}") from exc

    if source == destination:
        raise ValueError("Source and destination must differ")
    if type(amount) is not int or amount <= 0:
        raise ValueError("amount_cents must be a positive integer")
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
        raise ValueError("currency must be a 3-letter code")
    return event_id


def record_processed_event(db: Session, envelope: dict) -> bool:
    """Record event id once. Caller must commit DB before Kafka offset."""
    event_id = validate_transfer_event(envelope)
    statement = (
        pg_insert(ProcessedEvent)
        .values(event_id=event_id, event_type="TransferPosted")
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(ProcessedEvent.event_id)
    )
    return db.scalar(statement) is not None
