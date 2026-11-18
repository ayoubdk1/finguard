import logging
import os
import re
import socket
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text

from app.core.logging import configure_json_logging, request_id_ctx
from app.core.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    OUTBOX_DEAD_COUNT,
    render_prometheus_metrics,
)
from app.db.session import SessionLocal, engine  # noqa: F401
from app.routers import accounts, admin, auth, fraud, transfers
from app.services.risk_assessment import assess_transaction_risk  # noqa: F401

configure_json_logging()
logger = logging.getLogger("finguard.http")


def validate_production_config() -> None:
    if os.getenv("FINGUARD_ENV", "development").lower() != "production":
        return
    jwt_secret = os.getenv("FINGUARD_JWT_SECRET", "").strip()
    if not jwt_secret or jwt_secret == "dev-only-insecure-secret-key-change-me-32chars" or len(jwt_secret) < 32:  # noqa: S105
        raise RuntimeError("FATAL: FINGUARD_JWT_SECRET must be at least 32 chars and non-default in production")
    if os.getenv("FINGUARD_DEMO_MODE") == "1":
        raise RuntimeError("FATAL: FINGUARD_DEMO_MODE=1 cannot be enabled in production")
    cors_raw = os.getenv("FINGUARD_CORS_ORIGINS", "")
    if "*" in [o.strip() for o in cors_raw.split(",")]:
        raise RuntimeError("FATAL: Wildcard CORS origin (*) is forbidden in production")
    if not os.getenv("FINGUARD_MFA_ENCRYPTION_KEY", "").strip():
        raise RuntimeError("FATAL: FINGUARD_MFA_ENCRYPTION_KEY must be set in production")


validate_production_config()

_is_prod = os.getenv("FINGUARD_ENV", "development").lower() == "production"
app = FastAPI(
    title="FinGuard API",  # gitleaks:allow
    docs_url=None if _is_prod else "/docs",  # gitleaks:allow
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

_allowed_origins = [
    o.strip()
    for o in os.getenv(
        "FINGUARD_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def observability_and_security_middleware(request: Request, call_next):
    raw_req_id = (request.headers.get("X-Request-ID") or "").strip()
    req_id = raw_req_id if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", raw_req_id) else str(uuid.uuid4())
    request.state.request_id = req_id
    token = request_id_ctx.set(req_id)
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
    finally:
        request_id_ctx.reset(token)

    duration = max(0.0, time.perf_counter() - start_time)
    response.headers["X-Request-ID"] = req_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = (
        "max-age=63072000; includeSubDomains; preload"
    )
    if request.url.path in ("/docs", "/redoc"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "frame-ancestors 'none'"
        )
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; frame-ancestors 'none'"
        )

    route = request.scope.get("route")
    path = getattr(route, "path", "unmatched")

    HTTP_REQUESTS_TOTAL.labels(
        method=request.method,
        path=path,
        status=str(response.status_code),
    ).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=request.method,
        path=path,
    ).observe(duration)

    return response


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/health/ready")
def readiness_check():
    checks: dict[str, str] = {}
    is_ready = True

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "error"
        is_ready = False

    try:
        from app.security.rate_limit import _get_redis_client

        r = _get_redis_client()
        if r is not None and r.ping():
            checks["redis"] = "ok"
        else:
            checks["redis"] = "disabled"
    except Exception:
        checks["redis"] = "degraded"

    from app.services.ml_risk import is_fraud_model_ready
    checks["fraud_model"] = "ok" if is_fraud_model_ready() else "missing_or_invalid"

    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory

        ini_path = Path(__file__).resolve().parents[1] / "alembic.ini"
        cfg = Config(str(ini_path))
        cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
        head_rev = ScriptDirectory.from_config(cfg).get_current_head()
        with engine.connect() as conn:
            current_rev = MigrationContext.configure(conn).get_current_revision()
        if current_rev == head_rev:
            checks["migrations"] = "ok"
        else:
            checks["migrations"] = "out_of_date"
            is_ready = False
    except Exception:
        checks["migrations"] = "error"
        is_ready = False

    streaming_on = os.getenv("FINGUARD_STREAMING_ENABLED", "0") == "1"
    kafka_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "").strip()
    if streaming_on or kafka_servers:
        target = kafka_servers.split(",")[0].strip() if kafka_servers else "127.0.0.1:9092"
        host, _, port_str = target.partition(":")
        try:
            with socket.create_connection((host, int(port_str or 9092)), timeout=1.0):
                checks["kafka"] = "ok"
        except Exception:
            checks["kafka"] = "unreachable"
            if streaming_on:
                is_ready = False
    else:
        checks["kafka"] = "disabled"

    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory

        ini_path = Path(__file__).resolve().parents[1] / "alembic.ini"
        cfg = Config(str(ini_path))
        cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
        head_rev = ScriptDirectory.from_config(cfg).get_current_head()
        with engine.connect() as conn:
            current_rev = MigrationContext.configure(conn).get_current_revision()
        if current_rev == head_rev:
            checks["migrations"] = "ok"
        else:
            checks["migrations"] = "out_of_date"
            is_ready = False
    except Exception:
        checks["migrations"] = "error"
        is_ready = False

    streaming_on = os.getenv("FINGUARD_STREAMING_ENABLED", "0") == "1"
    kafka_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "").strip()
    if streaming_on or kafka_servers:
        target = kafka_servers.split(",")[0].strip() if kafka_servers else "127.0.0.1:9092"
        host, _, port_str = target.partition(":")
        try:
            with socket.create_connection((host, int(port_str or 9092)), timeout=1.0):
                checks["kafka"] = "ok"
        except Exception:
            checks["kafka"] = "unreachable"
            if streaming_on:
                is_ready = False
    else:
        checks["kafka"] = "disabled"

    if not is_ready:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": checks},
        )
    return {"status": "ready", "checks": checks}


@app.get("/metrics")
def prometheus_metrics():
    try:
        from app.db.models import OutboxEvent, OutboxStatus

        with SessionLocal() as db:
            dead = int(db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status == OutboxStatus.DEAD)) or 0)
            OUTBOX_DEAD_COUNT.set(dead)
    except Exception as exc:
        logger.warning("Failed to collect outbox dead count: %s", exc)
    payload, content_type = render_prometheus_metrics()
    return Response(content=payload, media_type=content_type)


app.include_router(auth.router, tags=["auth"])
app.include_router(accounts.router, tags=["accounts"])
app.include_router(transfers.router, tags=["transfers"])
app.include_router(fraud.router, tags=["fraud"])
app.include_router(admin.router, tags=["admin"])
