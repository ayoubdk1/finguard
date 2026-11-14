import json
import logging
from pathlib import Path
import uuid

from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app.core.logging import JsonFormatter, request_id_ctx
from app.db.models import OutboxEvent, OutboxStatus
from app.db.session import engine
from app.main import app
from app.security.rate_limit import LOGIN_MAX_ATTEMPTS, reset_login_rate_limits
from app.services.event_streaming import publish_batch
from app.services.resilience import calculate_backoff_delay

client = TestClient(app)


class AlwaysFailingProducer:
    def produce(self, *, topic, key, value, on_delivery):
        self._cb = on_delivery

    def flush(self, timeout):
        self._cb(RuntimeError("broker down"), None)
        return 0


def test_request_id_middleware_and_json_log_propagation():
    custom_id = "req-p3-check-12345"
    res = client.get("/health", headers={"X-Request-ID": custom_id})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == custom_id

    res_auto = client.get("/health")
    assert res_auto.status_code == 200
    assert res_auto.headers.get("X-Request-ID")

    token = request_id_ctx.set(custom_id)
    try:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="finguard.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello with request id",
            args=(),
            exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        assert parsed["request_id"] == custom_id
    finally:
        request_id_ctx.reset(token)


def test_backoff_jitter_adds_bounded_randomness():
    d_no_jitter = calculate_backoff_delay(2, base_delay_seconds=1.0, max_delay_seconds=10.0)
    assert d_no_jitter == 2.0

    d_jitter = calculate_backoff_delay(
        2,
        base_delay_seconds=1.0,
        max_delay_seconds=10.0,
        jitter_ratio=0.5,
        rng=lambda: 0.5,
    )
    assert d_jitter == 2.5


def test_prometheus_client_histograms_and_counters_exposed(client):
    reset_login_rate_limits()
    for _ in range(LOGIN_MAX_ATTEMPTS + 1):
        client.post(
            "/auth/login",
            json={"email": "ratelimit-metric@example.com", "password": "WrongPassword!123"},
        )

    r_assess = client.post(
        "/risk/assess",
        json={
            "amount_cents": 150000,
            "transfers_last_10min": 4,
            "account_age_minutes": 30,
            "failed_transfers_last_hour": 2,
        },
    )

    assert r_assess.status_code == 200, r_assess.text
    metrics_res = client.get("/metrics")
    assert metrics_res.status_code == 200
    text = metrics_res.text
    assert "finguard_http_requests_total" in text
    assert "finguard_http_request_duration_seconds_bucket" in text
    assert "finguard_fraud_risk_score_bucket" in text
    assert "finguard_rate_limit_hits_total" in text


def test_outbox_publisher_marks_dead_after_max_attempts():
    assert engine.url.database == "finguard_test"
    with engine.connect() as conn:
        outer = conn.begin()
        factory = lambda: Session(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            event_id = uuid.uuid4()
            with factory() as db:
                with db.begin():
                    db.add(
                        OutboxEvent(
                            id=event_id,
                            aggregate_id=uuid.uuid4(),
                            correlation_id=uuid.uuid4(),
                            event_type="TransferPosted",
                            event_version=1,
                            payload={
                                "transaction_id": str(uuid.uuid4()),
                                "source_account_id": str(uuid.uuid4()),
                                "destination_account_id": str(uuid.uuid4()),
                                "amount_cents": 5000,
                                "currency": "USD",
                            },
                            publish_attempts=0,
                            status=OutboxStatus.PENDING.value,
                        )
                    )

            failing = AlwaysFailingProducer()
            for _ in range(3):
                assert publish_batch(failing, session_factory=factory, max_attempts=3) == 0

            with factory() as db:
                ev = db.get(OutboxEvent, event_id)
                assert ev is not None
                assert ev.publish_attempts == 3
                assert ev.status == OutboxStatus.DEAD.value
                assert ev.last_error is not None

            # Subsequent batch must skip DEAD events
            assert publish_batch(failing, session_factory=factory, max_attempts=3) == 0
            with factory() as db:
                ev = db.get(OutboxEvent, event_id)
                assert ev.publish_attempts == 3
        finally:
            if outer.is_active:
                outer.rollback()


def test_routers_and_grafana_dashboard_exist():
    root = Path(__file__).resolve().parents[2]
    for rname in ("auth", "accounts", "transfers", "fraud", "admin"):
        assert (root / "backend" / "app" / "routers" / f"{rname}.py").exists()

    dash_path = root / "monitoring" / "grafana" / "dashboards" / "finguard-overview.json"
    assert dash_path.exists()
    dash = json.loads(dash_path.read_text(encoding="utf-8"))
    assert dash["uid"] == "finguard-p3-overview"
    assert len(dash["panels"]) >= 4
