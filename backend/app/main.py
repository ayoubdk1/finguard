import logging
import os
import time
import uuid

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.logging import configure_json_logging, request_id_ctx
from app.core.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    render_prometheus_metrics,
)
from app.db.session import SessionLocal, engine
from app.services.risk_assessment import assess_transaction_risk  # noqa: F401
from app.routers import accounts, admin, auth, fraud, transfers

configure_json_logging()
logger = logging.getLogger("finguard.http")

app = FastAPI(title="FinGuard API")

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
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
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

    if not is_ready:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": checks},
        )
    return {"status": "ready", "checks": checks}


@app.get("/metrics")
def prometheus_metrics():
    payload, content_type = render_prometheus_metrics()
    return Response(content=payload, media_type=content_type)


app.include_router(auth.router, tags=["auth"])
app.include_router(accounts.router, tags=["accounts"])
app.include_router(transfers.router, tags=["transfers"])
app.include_router(fraud.router, tags=["fraud"])
app.include_router(admin.router, tags=["admin"])
