"""The per-address sign-in throttle."""

from __future__ import annotations

from shabetz.auth.throttle import FailureThrottle
from shabetz.config import Settings


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_blocks_after_the_limit_within_the_window() -> None:
    throttle = FailureThrottle(max_failures=3, window_seconds=60, clock=FakeClock())
    for _ in range(2):
        throttle.record_failure("1.2.3.4")
    assert not throttle.is_blocked("1.2.3.4")
    throttle.record_failure("1.2.3.4")
    assert throttle.is_blocked("1.2.3.4")


def test_addresses_are_independent() -> None:
    throttle = FailureThrottle(max_failures=2, window_seconds=60, clock=FakeClock())
    throttle.record_failure("attacker")
    throttle.record_failure("attacker")
    assert throttle.is_blocked("attacker")
    assert not throttle.is_blocked("real-owner")


def test_failures_expire_after_the_window() -> None:
    clock = FakeClock()
    throttle = FailureThrottle(max_failures=2, window_seconds=60, clock=clock)
    throttle.record_failure("x")
    throttle.record_failure("x")
    assert throttle.is_blocked("x")
    clock.now += 61
    assert not throttle.is_blocked("x")


def test_retry_after_counts_down_to_the_oldest_failure_expiring() -> None:
    clock = FakeClock()
    throttle = FailureThrottle(max_failures=2, window_seconds=60, clock=clock)
    throttle.record_failure("x")
    clock.now += 20
    throttle.record_failure("x")
    assert 39 <= throttle.retry_after_seconds("x") <= 41
    assert throttle.retry_after_seconds("never-failed") == 0


def test_expired_addresses_do_not_accumulate() -> None:
    clock = FakeClock()
    throttle = FailureThrottle(max_failures=5, window_seconds=10, clock=clock)
    for index in range(100):
        throttle.record_failure(f"addr-{index}")
    clock.now += 11
    for index in range(100):
        throttle.is_blocked(f"addr-{index}")
    assert len(throttle._failures) == 0


def test_default_address_limit_is_below_the_account_limit() -> None:
    """Reversed, a single attacker could lock the real owner out of their account."""
    defaults = Settings()
    assert defaults.login_ip_max_failures < defaults.login_max_attempts
