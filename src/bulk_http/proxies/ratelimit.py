"""A per-domain rate limiter enforcing a minimum interval between requests."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]


class DomainRateLimiter:
    """Space out requests per domain to at most ``rate`` per second.

    Each domain is tracked independently; :meth:`acquire` sleeps just long enough
    to honour the ``1/rate`` minimum interval since the previous grant for that
    domain. The clock and sleep are injectable for deterministic testing.
    """

    def __init__(
        self,
        rate: float,
        *,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate must be > 0")
        self._interval = 1.0 / rate
        self._clock = clock
        self._sleep = sleep
        self._next: dict[str, float] = {}

    async def acquire(self, domain: str) -> None:
        now = self._clock()
        earliest = self._next.get(domain, 0.0)
        start = max(now, earliest)
        wait = start - now
        if wait > 0:
            await self._sleep(wait)
        self._next[domain] = start + self._interval
