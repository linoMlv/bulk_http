"""Adaptive per-domain rate limiting (AIMD) with ban detection.

Optional. When enabled, the limiter starts at ``start_rate`` req/s per domain and
adjusts itself: it nudges the rate up after a run of clean responses (additive
increase) and halves it on a 429 or transport error (multiplicative decrease),
staying within ``[min_rate, max_rate]``. If, once already at the minimum rate,
failures still dominate a sliding window, a ban is suspected and
:class:`BanSuspectedError` is raised to stop the campaign.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]

_FAILURE_OUTCOMES = frozenset({"rate_limited", "transport_error"})


class BanSuspectedError(RuntimeError):
    """Raised when failures persist at the minimum rate (likely an IP ban)."""


@dataclass(frozen=True, slots=True)
class AdaptiveRateConfig:
    """Tuning for the adaptive limiter (all plain data, picklable for spawn)."""

    start_rate: float = 10.0
    min_rate: float = 1.0
    max_rate: float = 50.0
    increase_step: float = 1.0
    increase_after: int = 20
    decrease_factor: float = 0.5
    ban_window: int = 30
    ban_failures: int = 20

    def __post_init__(self) -> None:
        if not (0 < self.min_rate <= self.start_rate <= self.max_rate):
            raise ValueError("require 0 < min_rate <= start_rate <= max_rate")
        if not (0 < self.decrease_factor < 1):
            raise ValueError("decrease_factor must be in (0, 1)")
        if self.increase_after < 1 or self.increase_step <= 0:
            raise ValueError("increase_after >= 1 and increase_step > 0")
        if self.ban_window < 1 or not (1 <= self.ban_failures <= self.ban_window):
            raise ValueError("require 1 <= ban_failures <= ban_window")


class AdaptiveRateLimiter:
    """A self-tuning per-domain limiter. ``acquire`` paces, ``record`` adapts."""

    def __init__(
        self,
        config: AdaptiveRateConfig,
        *,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._c = config
        self._clock = clock
        self._sleep = sleep
        self._rate: dict[str, float] = {}
        self._next: dict[str, float] = {}
        self._successes: dict[str, int] = {}
        self._window: dict[str, deque[bool]] = {}

    def rate(self, domain: str) -> float:
        return self._rate.get(domain, self._c.start_rate)

    async def acquire(self, domain: str) -> None:
        interval = 1.0 / self.rate(domain)
        now = self._clock()
        earliest = self._next.get(domain, 0.0)
        start = max(now, earliest)
        self._next[domain] = start + interval  # reserve before sleeping
        wait = start - now
        if wait > 0:
            await self._sleep(wait)

    def record(self, domain: str, outcome: str) -> None:
        failure = outcome in _FAILURE_OUTCOMES
        window = self._window.setdefault(domain, deque(maxlen=self._c.ban_window))
        window.append(failure)
        if failure:
            self._successes[domain] = 0
            new_rate = max(self._c.min_rate, self.rate(domain) * self._c.decrease_factor)
            self._rate[domain] = new_rate
            if new_rate <= self._c.min_rate and sum(window) >= self._c.ban_failures:
                raise BanSuspectedError(
                    f"failures persist for {domain!r} at the minimum rate; stopping"
                )
        elif outcome == "ok":
            streak = self._successes.get(domain, 0) + 1
            if streak >= self._c.increase_after:
                self._rate[domain] = min(
                    self._c.max_rate, self.rate(domain) + self._c.increase_step
                )
                streak = 0
            self._successes[domain] = streak
