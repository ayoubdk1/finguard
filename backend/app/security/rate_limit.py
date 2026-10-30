import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 60.0

_login_attempts: dict[str, list[float]] = defaultdict(list)


def check_login_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window_start = now - LOGIN_WINDOW_SECONDS

    recent = [t for t in _login_attempts[client_ip] if t > window_start]
    if len(recent) >= LOGIN_MAX_ATTEMPTS:
        _login_attempts[client_ip] = recent
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )

    recent.append(now)
    _login_attempts[client_ip] = recent


def reset_login_rate_limits() -> None:
    _login_attempts.clear()

