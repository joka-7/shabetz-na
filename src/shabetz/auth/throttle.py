"""Per-address throttling of failed sign-ins.

Account lockout alone is a weapon on the open internet: anyone who knows the
administrator's email can lock them out by guessing wrong a few times. This
throttle is checked before a password is verified, so once an address is
blocked its further guesses never reach the account's own counter. The attacker
slows themselves down instead of locking out their target.

State is per process. Behind several workers the effective limit is multiplied
by the worker count, which still bounds guessing to a few hundred attempts per
window rather than unlimited.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable


class FailureThrottle:
    def __init__(
        self,
        max_failures: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        entries = self._failures[key]
        while entries and now - entries[0] > self._window:
            entries.popleft()
        if not entries:
            # Keep the map from growing with every address ever seen.
            self._failures.pop(key, None)
            return deque()
        return entries

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key, self._clock())) >= self._max

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            self._prune(key, now)
            self._failures[key].append(now)

    def retry_after_seconds(self, key: str) -> int:
        with self._lock:
            entries = self._prune(key, self._clock())
            if len(entries) < self._max:
                return 0
            return max(1, int(self._window - (self._clock() - entries[0])) + 1)
