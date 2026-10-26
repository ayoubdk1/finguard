"""Run from backend/: python -m scripts.consume_transfers"""
import json
from datetime import datetime, timezone

from confluent_kafka import Consumer, KafkaException

from app.db.session import SessionLocal
from app.services.event_streaming import (
    BROKER, TOPIC, DLQ_TOPIC, new_producer, record_processed_event, send_json,
    validate_transfer_event,
)


def main():
    consumer = Consumer({
        "bootstrap.servers": BROKER,
        "broker.address.family": "v4",
        "group.id": "finguard-transfer-audit-v1",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
        "enable.auto.offset.store": False,
    })
    dlq_producer = new_producer()
    consumer.subscribe([TOPIC])
    print(f"Listening to {TOPIC}; Ctrl+C to stop")
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                raise KafkaException(msg.error())

            try:
                envelope = json.loads(msg.value().decode("utf-8"))
                validate_transfer_event(envelope)
            except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
                # Malformed messages go to DLQ. Commit source offset only if DLQ is acknowledged.
                dlq_payload = {
                    "raw_value": msg.value().decode("utf-8", errors="replace"),
                    "error": str(exc),
                    "source_topic": msg.topic(),
                    "partition": msg.partition(),
                    "offset": msg.offset(),
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                }
                send_json(dlq_producer, DLQ_TOPIC, f"bad-{msg.partition()}-{msg.offset()}", dlq_payload)
                print(f"Invalid event -> DLQ: {exc}")
                consumer.commit(message=msg, asynchronous=False)
                continue

            # A database problem must NOT commit the source offset.
            with SessionLocal.begin() as db:
                first_time = record_processed_event(db, envelope)
            consumer.commit(message=msg, asynchronous=False)
            print(f"{'Processed' if first_time else 'Duplicate ignored'}: {envelope['event_id']}")

    except KeyboardInterrupt:
        print("Consumer stopped")
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
