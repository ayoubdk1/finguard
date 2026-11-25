import hashlib
import ipaddress
import logging
import os
import threading
import time
import uuid
from collections import defaultdict

import redis
from fastapi import HTTPException, Request, status

from app.core.metrics import RATE_LIMIT_HITS_TOTAL
from app.services.resilience import CircuitBreaker, CircuitBreakerOpenError, retry_with_backoff

logger = logging.getLogger("finguard.ratelimit")

LOGIN_MAX_ATTEMPTS = int(os.getenv("FINGUARD_LOGIN_RATE_LIMIT_MAX", "5"))
LOGIN_WINDOW_SECONDS = float(os.getenv("FINGUARD_LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60"))
MFA_MAX_ATTEMPTS = int(os.getenv("FINGUARD_MFA_RATE_LIMIT_MAX", "5"))
MFA_WINDOW_SECONDS = float(os.getenv("FINGUARD_MFA_RATE_LIMIT_WINDOW_SECONDS", "60"))
REFRESH_MAX_ATTEMPTS = int(os.getenv("FINGUARD_REFRESH_RATE_LIMIT_MAX", "10"))
REFRESH_WINDOW_SECONDS = float(os.getenv("FINGUARD_REFRESH_RATE_LIMIT_WINDOW_SECONDS", "60"))

_buckets: dict[str, list[float]] = defaultdict(list)
_lock = threading.Lock()
redis_circuit_breaker = CircuitBreaker(name="redis-ratelimit", failure_threshold=2, recovery_timeout_seconds=10.0)


def _get_redis_client() -> redis.Redis | None:
    redis_url = os.getenv("FINGUARD_REDIS_URL", "redis://localhost:6379/0").strip()
    if not redis_url:
        return None
    return redis.Redis.from_url(redis_url, socket_connect_timeout=0.3, socket_timeout=0.3, decode_responses=True)


def _is_trusted_proxy(host: str) -> bool:
    env = os.getenv("FINGUARD_ENV", "development").lower()
    raw = os.getenv("FINGUARD_TRUSTED_PROXIES", "127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16" + (",testclient" if env != "production" else ""))
    entries = [e.strip() for e in raw.split(",") if e.strip()]
    if host in entries:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    for e in entries:
        try:
            if "/" in e and ip in ipaddress.ip_network(e, strict=False):
                return True
            if "/" not in e and ip == ipaddress.ip_address(e):
                return True
        except ValueError:
            continue
    return False


def extract_client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    if not _is_trusted_proxy(peer):
        return peer
    xff = request.headers.get("x-forwarded-for", "").strip()
    if not xff:
        return peer
    hops = [h.strip() for h in xff.split(",") if h.strip()]
    for hop in reversed(hops):
        if not _is_trusted_proxy(hop):
            return hop
    return hops[0] if hops else peer


def _check_in_memory(bucket_key: str, max_attempts: int, window_seconds: float, detail: str) -> None:
    now = time.monotonic()
    window_start = now - window_seconds
    with _lock:
        recent = [t for t in _buckets[bucket_key] if t > window_start]
        if len(recent) >= max_attempts:
            _buckets[bucket_key] = recent
            RATE_LIMIT_HITS_TOTAL.labels(limiter="in_memory_sliding").inc()
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail, headers={"Retry-After": str(max(1, int(window_seconds)))})
        recent.append(now)
        _buckets[bucket_key] = recent


def check_rate_limit(bucket: str, key: str, max_attempts: int, window_seconds: float, detail: str = "Too many requests.") -> None:
    bucket_key = f"{bucket}:{key}"
    client = _get_redis_client()
    if client is not None:
        redis_key = f"finguard:ratelimit:{bucket_key}"
        now_ms = int(time.time() * 1000)
        window_start_ms = now_ms - int(window_seconds * 1000)
        member = f"{now_ms}:{uuid.uuid4().hex[:8]}"

        def _exec() -> int:
            pipe = client.pipeline()
            pipe.zremrangebyscore(redis_key, "-inf", window_start_ms)
            pipe.zcard(redis_key)
            _, current_count = pipe.execute()
            if int(current_count) >= max_attempts:
                return int(current_count) + 1
            pipe2 = client.pipeline()
            pipe2.zadd(redis_key, {member: now_ms})
            pipe2.expire(redis_key, int(window_seconds) + 1)
            pipe2.execute()
            return int(current_count) + 1

        try:
            count = redis_circuit_breaker.call(lambda: retry_with_backoff(_exec, max_attempts=2, base_delay_seconds=0.02, max_delay_seconds=0.05, jitter_ratio=0.25))
            if count > max_attempts:
                RATE_LIMIT_HITS_TOTAL.labels(limiter="redis_sliding").inc()
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail, headers={"Retry-After": str(max(1, int(window_seconds)))})
            return
        except (redis.exceptions.RedisError, CircuitBreakerOpenError):
            pass
    _check_in_memory(bucket_key, max_attempts, window_seconds, detail)


def _email_bucket_key(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:32]


def check_login_rate_limit(request: Request, email: str | None = None) -> None:
    ip = extract_client_ip(request)
    check_rate_limit("login:ip", ip, LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW_SECONDS, "Too many login attempts. Please try again later.")


def record_failed_login_and_check_spray(email: str) -> None:
    if not email or not email.strip():
        return
    check_rate_limit("login:acct_fail", _email_bucket_key(email), LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW_SECONDS, "Too many failed login attempts for this account. Please try again later.")
    if email:
        acct_key = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:24]
        check_rate_limit("login:acct", acct_key, LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW_SECONDS, "Too many login attempts for this account.")


def check_mfa_rate_limit(account_key: str) -> None:
    check_rate_limit("mfa:acct", account_key, MFA_MAX_ATTEMPTS, MFA_WINDOW_SECONDS, "Too many MFA attempts. Please try again later.")


def check_refresh_rate_limit(family_key: str) -> None:
    check_rate_limit("refresh:family", family_key, REFRESH_MAX_ATTEMPTS, REFRESH_WINDOW_SECONDS, "Too many token refresh attempts.")


def reset_login_rate_limits() -> None:
    with _lock:
        _buckets.clear()
    redis_circuit_breaker.reset()
    client = _get_redis_client()
    if client is not None:
        try:
            keys = list(client.scan_iter("finguard:ratelimit:*"))
            if keys:
                client.delete(*keys)
        except redis.exceptions.RedisError:
            pass
