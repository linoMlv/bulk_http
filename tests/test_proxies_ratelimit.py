"""Tests for the per-domain rate limiter."""

import pytest

from bulk_http.proxies import DomainRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.t

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.t += delay


async def test_first_acquire_does_not_wait() -> None:
    clock = FakeClock()
    limiter = DomainRateLimiter(10.0, clock=clock.time, sleep=clock.sleep)
    await limiter.acquire("a.com")
    assert clock.sleeps == []


async def test_second_immediate_acquire_waits_one_interval() -> None:
    clock = FakeClock()
    limiter = DomainRateLimiter(10.0, clock=clock.time, sleep=clock.sleep)
    await limiter.acquire("a.com")
    await limiter.acquire("a.com")
    assert clock.sleeps == pytest.approx([0.1])


async def test_domains_are_independent() -> None:
    clock = FakeClock()
    limiter = DomainRateLimiter(10.0, clock=clock.time, sleep=clock.sleep)
    await limiter.acquire("a.com")
    await limiter.acquire("b.com")
    assert clock.sleeps == []


async def test_no_wait_when_enough_time_elapsed() -> None:
    clock = FakeClock()
    limiter = DomainRateLimiter(10.0, clock=clock.time, sleep=clock.sleep)
    await limiter.acquire("a.com")
    clock.t += 1.0  # plenty of time passes
    await limiter.acquire("a.com")
    assert clock.sleeps == []


async def test_sustained_rate_spaces_requests() -> None:
    clock = FakeClock()
    limiter = DomainRateLimiter(5.0, clock=clock.time, sleep=clock.sleep)  # 0.2s interval
    for _ in range(4):
        await limiter.acquire("a.com")
    assert clock.sleeps == pytest.approx([0.2, 0.2, 0.2])


def test_invalid_rate_rejected() -> None:
    with pytest.raises(ValueError):
        DomainRateLimiter(0.0)


class FrozenClock:
    def __init__(self) -> None:
        self.waits: list[float] = []

    def time(self) -> float:
        return 0.0

    async def sleep(self, delay: float) -> None:
        import asyncio

        self.waits.append(delay)
        await asyncio.sleep(0)  # yield to the loop so other coroutines interleave


async def test_concurrent_acquires_are_serialized() -> None:
    import asyncio

    clock = FrozenClock()
    limiter = DomainRateLimiter(10.0, clock=clock.time, sleep=clock.sleep)  # 0.1s interval
    # Five coroutines hitting the same domain at once must each get a distinct slot.
    await asyncio.gather(*(limiter.acquire("a.com") for _ in range(5)))
    assert clock.waits == pytest.approx([0.1, 0.2, 0.3, 0.4])
