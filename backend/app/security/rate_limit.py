import logging
import os
import threading
import time
import uuid
from collections import defaultdict

from fastapi import HTTPException, Request, status
import redis

from app.core.metrics import RATE_LIMIT_HITS_TOTAL
from app.services.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    retry_with_backoff,
)

logger = logging.getLogger("finguard.ratelimit")

LOGIN_MAX_ATTEMPTS = int(os.getenv("FINGUARD_LOGIN_RATE_LIMIT_MAX", "5"))
LOGIN_WINDOW_SECONDS = float(
    os.getenv("FINGUARD_LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60")
)
REDIS_KEY_PREFIX = "finguard:ratelimit:sliding:login:"

_login_attempts: dict[str, list[float]] = defaultdict(list)
_lock = threading.Lock()

redis_circuit_breaker = CircuitBreaker(
    name="redis-ratelimit",
    failure_threshold=2,
    recovery_timeout_seconds=10.0,
)


def _get_redis_client() -> redis.Redis | None:
    redis_url = os.getenv("FINGUARD_REDIS_URL", "redis://localhost:6379/0").strip()
    if not redis_url:
        return None
    return redis.Redis.from_url(
        redis_url,
        socket_connect_timeout=0.3,
        socket_timeout=0.3,
        decode_responses=True,
    )


def _check_in_memory_sliding_window(client_ip: str) -> None:
    now = time.monotonic()
    window_start = now - LOGIN_WINDOW_SECONDS

    with _lock:
        recent = [t for t in _login_attempts[client_ip] if t > window_start]
        if len(recent) >= LOGIN_MAX_ATTEMPTS:
            _login_attempts[client_ip] = recent
            RATE_LIMIT_HITS_TOTAL.labels(limiter="in_memory_sliding").inc()
            logger.warning(f"Rate limit exceeded (in-memory) for IP {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Please try again later.",
                headers={"Retry-After": str(int(LOGIN_WINDOW_SECONDS))},
            )
        recent.append(now)
        _login_attempts[client_ip] = recent


def check_login_rate_limit(request: Request) -> None:
    """Sliding-window rate limiter backed by a Redis sorted set (ZSET)."""
    client_ip = request.client.host if request.client else "unknown"
    client = _get_redis_client()

    if client is not None:
        key = f"{REDIS_KEY_PREFIX}{client_ip}"
        now_ms = int(time.time() * 1000)
        window_start_ms = now_ms - int(LOGIN_WINDOW_SECONDS * 1000)
        member = f"{now_ms}:{uuid.uuid4().hex[:8]}"

        def _exec_sliding_window() -> int:
            pipe = client.pipeline()
            pipe.zremrangebyscore(key, "-inf", window_start_ms)
            pipe.zcard(key)
            _, current_count = pipe.execute()
            if int(current_count) >= LOGIN_MAX_ATTEMPTS:
                return int(current_count) + 1
            pipe2 = client.pipeline()
            pipe2.zadd(key, {member: now_ms})
            pipe2.expire(key, int(LOGIN_WINDOW_SECONDS) + 1)
            pipe2.execute()
            return int(current_count) + 1

        try:
            count = redis_circuit_breaker.call(
                lambda: retry_with_backoff(
                    _exec_sliding_window,
                    max_attempts=2,
                    base_delay_seconds=0.02,
                    max_delay_seconds=0.05,
                    jitter_ratio=0.25,
                )
            )
            if count > LOGIN_MAX_ATTEMPTS:
                RATE_LIMIT_HITS_TOTAL.labels(limiter="redis_sliding").inc()
                logger.warning(f"Rate limit exceeded (redis sliding window) for IP {client_ip}")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many login attempts. Please try again later.",
                    headers={"Retry-After": str(int(LOGIN_WINDOW_SECONDS))},
                )
            return
        except (redis.exceptions.RedisError, CircuitBreakerOpenError):
            pass

    _check_in_memory_sliding_window(client_ip)


def reset_login_rate_limits() -> None:
    with _lock:
        _login_attempts.clear()
    redis_circuit_breaker.reset()

    client = _get_redis_client()
    if client is not None:
        try:
            keys = list(client.scan_iter("finguard:ratelimit:*"))
            if keys:
                client.delete(*keys)
        except redis.exceptions.RedisError:
            pass
