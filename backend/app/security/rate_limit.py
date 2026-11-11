import os
import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status
import redis

LOGIN_MAX_ATTEMPTS = int(os.getenv("FINGUARD_LOGIN_RATE_LIMIT_MAX", "5"))
LOGIN_WINDOW_SECONDS = float(
    os.getenv("FINGUARD_LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60")
)
REDIS_KEY_PREFIX = "finguard:ratelimit:login:"

_login_attempts: dict[str, list[float]] = defaultdict(list)
_lock = threading.Lock()


def _get_redis_client() -> redis.Redis | None:
    redis_url = os.getenv("FINGUARD_REDIS_URL", "redis://localhost:6379/0").strip()
    if not redis_url:
        return None
    return redis.Redis.from_url(
        redis_url,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
        decode_responses=True,
    )


def _check_in_memory(client_ip: str) -> None:
    now = time.monotonic()
    window_start = now - LOGIN_WINDOW_SECONDS

    with _lock:
        recent = [t for t in _login_attempts[client_ip] if t > window_start]
        if len(recent) >= LOGIN_MAX_ATTEMPTS:
            _login_attempts[client_ip] = recent
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Please try again later.",
                headers={"Retry-After": str(int(LOGIN_WINDOW_SECONDS))},
            )
        recent.append(now)
        _login_attempts[client_ip] = recent


def check_login_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    client = _get_redis_client()

    if client is not None:
        key = f"{REDIS_KEY_PREFIX}{client_ip}"
        try:
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, int(LOGIN_WINDOW_SECONDS), nx=True)
            count, _ = pipe.execute()

            if int(count) > LOGIN_MAX_ATTEMPTS:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many login attempts. Please try again later.",
                    headers={"Retry-After": str(int(LOGIN_WINDOW_SECONDS))},
                )
            return
        except redis.exceptions.RedisError:
            # Graceful fallback to in-memory limiter if Redis is unavailable
            pass

    _check_in_memory(client_ip)


def reset_login_rate_limits() -> None:
    with _lock:
        _login_attempts.clear()

    client = _get_redis_client()
    if client is not None:
        try:
            keys = list(client.scan_iter(f"{REDIS_KEY_PREFIX}*"))
            if keys:
                client.delete(*keys)
        except redis.exceptions.RedisError:
            pass
