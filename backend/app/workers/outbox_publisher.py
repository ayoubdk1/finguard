"""Standalone outbox publisher worker process for Docker Compose."""

import logging
import os
import signal
import time

from app.core.logging import configure_json_logging
from app.services.event_streaming import (
    DEFAULT_MAX_ATTEMPTS,
    new_producer,
    publish_batch,
)

configure_json_logging()
logger = logging.getLogger("finguard.worker.outbox")

_running = True


def _handle_stop(signum, frame):
    global _running
    logger.info("Shutting down outbox publisher worker...")
    _running = False


def run_worker(poll_interval_seconds: float = 2.0) -> None:
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)
    producer = new_producer()
    logger.info("Started FinGuard outbox publisher worker")

    while _running:
        try:
            count = publish_batch(
                producer,
                batch_size=20,
                max_attempts=DEFAULT_MAX_ATTEMPTS,
                base_backoff_seconds=1.0,
                jitter_ratio=0.25,
                use_circuit_breaker=True,
            )
            if count > 0:
                logger.info(f"Published {count} outbox event(s)")
        except Exception as exc:
            logger.error(f"Outbox worker iteration error: {exc}")
        time.sleep(poll_interval_seconds)


if __name__ == "__main__":
    interval = float(os.getenv("FINGUARD_OUTBOX_POLL_SECONDS", "2.0"))
    run_worker(poll_interval_seconds=interval)
