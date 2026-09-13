"""Tests for the async robots gate (fetch, cache, allow, crawl-delay)."""

from collections.abc import Awaitable, Callable

from bulk_http.compliance import AsyncRobotsGate

ROBOTS = "User-agent: *\nDisallow: /admin\nCrawl-delay: 2\n"


def _fetcher(content: str | None, calls: list[str]) -> Callable[[str], Awaitable[str | None]]:
    async def fetch(url: str) -> str | None:
        calls.append(url)
        return content

    return fetch


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def time(self) -> float:
        return self.t

    async def sleep(self, delay: float) -> None:
        self.t += delay


async def test_allowed_respects_disallow() -> None:
    gate = AsyncRobotsGate(_fetcher(ROBOTS, []))
    assert await gate.allowed("https://a.com/admin/panel") is False
    assert await gate.allowed("https://a.com/public") is True


async def test_missing_robots_allows_all() -> None:
    gate = AsyncRobotsGate(_fetcher(None, []))
    assert await gate.allowed("https://a.com/admin") is True


async def test_robots_cached_per_origin() -> None:
    calls: list[str] = []
    gate = AsyncRobotsGate(_fetcher(ROBOTS, calls))
    await gate.allowed("https://a.com/x")
    await gate.allowed("https://a.com/y")
    await gate.allowed("https://b.com/z")
    assert len(calls) == 2
    assert calls[0].endswith("/robots.txt")


async def test_throttle_applies_crawl_delay() -> None:
    clock = FakeClock()
    gate = AsyncRobotsGate(_fetcher(ROBOTS, []), clock=clock.time, sleep=clock.sleep)
    await gate.throttle("https://a.com/1")  # first: no wait
    await gate.throttle("https://a.com/2")  # second: waits crawl-delay
    assert clock.t == 2.0


async def test_throttle_without_crawl_delay_is_noop() -> None:
    clock = FakeClock()
    gate = AsyncRobotsGate(
        _fetcher("User-agent: *\nDisallow:\n", []), clock=clock.time, sleep=clock.sleep
    )
    await gate.throttle("https://a.com/1")
    await gate.throttle("https://a.com/2")
    assert clock.t == 0.0


async def test_throttle_without_robots_is_noop() -> None:
    clock = FakeClock()
    gate = AsyncRobotsGate(_fetcher(None, []), clock=clock.time, sleep=clock.sleep)
    await gate.throttle("https://a.com/1")
    await gate.throttle("https://a.com/2")
    assert clock.t == 0.0
