import random
import threading
import time
from collections.abc import Callable
from enum import StrEnum
from typing import TypeVar

T = TypeVar("T")


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(RuntimeError):
    """Raised when a call is blocked because the circuit breaker is OPEN."""


class CircuitBreaker:
    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if (
                self._state == CircuitState.OPEN
                and self._opened_at is not None
                and (self._clock() - self._opened_at) >= self.recovery_timeout_seconds
            ):
                self._state = CircuitState.HALF_OPEN
            return self._state

    def reset(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._state = CircuitState.CLOSED
            self._opened_at = None

    def call(self, fn: Callable[..., T], *args, **kwargs) -> T:
        current_state = self.state
        if current_state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.name}' is OPEN"
            )

        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._record_failure()
            raise

        self._record_success()
        return result

    def _record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            if (
                self._state == CircuitState.HALF_OPEN
                or self._failure_count >= self.failure_threshold
            ):
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()

    def _record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._state = CircuitState.CLOSED
            self._opened_at = None


def calculate_backoff_delay(
    attempt: int,
    base_delay_seconds: float = 0.5,
    max_delay_seconds: float = 60.0,
    jitter_ratio: float = 0.0,
    rng: Callable[[], float] = random.random,
) -> float:
    if attempt <= 0:
        return 0.0
    delay = base_delay_seconds * (2 ** (attempt - 1))
    if jitter_ratio > 0.0:
        delay = delay * (1.0 + rng() * jitter_ratio)
    return min(max_delay_seconds, delay)


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay_seconds: float = 0.1,
    max_delay_seconds: float = 5.0,
    jitter_ratio: float = 0.0,
    rng: Callable[[], float] = random.random,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> T:
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            delay = calculate_backoff_delay(
                attempt,
                base_delay_seconds=base_delay_seconds,
                max_delay_seconds=max_delay_seconds,
                jitter_ratio=jitter_ratio,
                rng=rng,
            )
            sleep_fn(delay)
    assert last_exc is not None
    raise last_exc
