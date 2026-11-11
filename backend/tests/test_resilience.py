import pytest

from app.services.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    calculate_backoff_delay,
    retry_with_backoff,
)


def test_circuit_breaker_opens_blocks_and_recovers():
    now = [100.0]
    cb = CircuitBreaker(
        name="redpanda-broker",
        failure_threshold=2,
        recovery_timeout_seconds=10.0,
        clock=lambda: now[0],
    )

    def failing_call():
        raise ConnectionError("broker unreachable")

    with pytest.raises(ConnectionError):
        cb.call(failing_call)
    assert cb.state == CircuitState.CLOSED

    with pytest.raises(ConnectionError):
        cb.call(failing_call)
    assert cb.state == CircuitState.OPEN

    # While OPEN, call is rejected immediately without invoking target
    with pytest.raises(CircuitBreakerOpenError):
        cb.call(lambda: "should-not-run")

    # Advance clock past recovery timeout -> HALF_OPEN -> CLOSED on success
    now[0] += 11.0
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.call(lambda: "ok") == "ok"
    assert cb.state == CircuitState.CLOSED


def test_retry_with_backoff_succeeds_after_transient_errors():
    attempts = [0]
    sleeps = []

    def flaky():
        attempts[0] += 1
        if attempts[0] < 3:
            raise TimeoutError("transient timeout")
        return "published"

    result = retry_with_backoff(
        flaky,
        max_attempts=4,
        base_delay_seconds=0.5,
        max_delay_seconds=4.0,
        sleep_fn=sleeps.append,
    )
    assert result == "published"
    assert attempts[0] == 3
    assert sleeps == [0.5, 1.0]


def test_calculate_backoff_delay_caps_at_max():
    assert calculate_backoff_delay(0) == 0.0
    assert calculate_backoff_delay(1, base_delay_seconds=1.0, max_delay_seconds=5.0) == 1.0
    assert calculate_backoff_delay(3, base_delay_seconds=1.0, max_delay_seconds=5.0) == 4.0
    assert calculate_backoff_delay(4, base_delay_seconds=1.0, max_delay_seconds=5.0) == 5.0
