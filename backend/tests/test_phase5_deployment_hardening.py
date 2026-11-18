import json
from pathlib import Path


def test_p5_health_ready_checks_migrations_and_kafka(client):
    r = client.get("/health/ready")
    assert r.status_code == 200
    checks = r.json()["checks"]
    assert checks["migrations"] == "ok"
    assert "kafka" in checks


def test_p5_swagger_csp_and_metrics_outbox_dead_gauge(client):
    r_docs = client.get("/docs")
    assert r_docs.status_code == 200
    csp = r_docs.headers.get("Content-Security-Policy", "")
    assert "cdn.jsdelivr.net" in csp

    r_api = client.get("/health")
    assert r_api.headers.get("Content-Security-Policy") == "default-src 'self'; frame-ancestors 'none'"

    r_metrics = client.get("/metrics")
    assert r_metrics.status_code == 200
    assert "finguard_outbox_dead_count" in r_metrics.text


def test_p5_deployment_files_hardened():
    root = Path(__file__).resolve().parents[2]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    assert ":latest" not in compose
    assert "change-me-in-production" not in compose
    assert "FINGUARD_JWT_SECRET: ${FINGUARD_JWT_SECRET:?" in compose
    assert "127.0.0.1:5433:5432" in compose
    assert "127.0.0.1:${REDIS_HOST_PORT:-6379}:6379" in compose
    assert "--requirepass" in compose
    assert "GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:?" in compose
    assert "condition: service_healthy" in compose

    dockerfile = (root / "backend" / "Dockerfile").read_text(encoding="utf-8")
    assert "AS builder" in dockerfile
    assert "USER appuser" in dockerfile
    dockerignore = (root / "backend" / ".dockerignore").read_text(encoding="utf-8")
    assert "tests/" in dockerignore
    assert "data/" in dockerignore

    env_ex = (root / ".env.example").read_text(encoding="utf-8")
    for var in ["FINGUARD_CORS_ORIGINS", "FINGUARD_MFA_ENCRYPTION_KEY", "FINGUARD_OUTBOX_MAX_ATTEMPTS", "FINGUARD_EXPOSE_RESET_TOKEN", "FINGUARD_DEMO_MODE"]:
        assert var in env_ex

    alerts = (root / "monitoring" / "prometheus" / "alerts.yml").read_text(encoding="utf-8")
    for rule in ["High5xxRate", "HighP95Latency", "OutboxDeadEvents", "LedgerReconciliationImbalance", "RateLimitSpike"]:
        assert rule in alerts

    dash = json.loads((root / "monitoring" / "grafana" / "dashboards" / "finguard-overview.json").read_text(encoding="utf-8"))
    titles = {p["title"] for p in dash["panels"]}
    assert "HTTP 5xx Error Rate" in titles
    assert "Outbox DEAD Events" in titles
