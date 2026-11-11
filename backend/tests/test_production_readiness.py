import json
import logging

from starlette.testclient import TestClient
from app.core.logging import JsonFormatter
from app.main import app

client = TestClient(app)


def test_health_and_readiness_endpoints():
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    ready = client.get("/health/ready")
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "ready"
    assert body["checks"]["postgres"] == "ok"


def test_json_log_formatter_outputs_valid_json():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="finguard.audit",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Transfer posted successfully",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)
    parsed = json.loads(formatted)
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "finguard.audit"
    assert parsed["message"] == "Transfer posted successfully"
    assert "timestamp" in parsed
