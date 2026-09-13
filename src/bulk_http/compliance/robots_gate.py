"""Async robots.txt gate: fetch, cache, allow decisions and crawl-delay.

Disabled by default; when the engine enables it, requests to disallowed paths are
skipped and per-host crawl-delays are honoured. The fetcher is injected (backed by
the transport in production, a stub in tests) so no network is needed to test the
gate itself.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

Fetcher = Callable[[str], Awaitable[str | None]]
Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]


class AsyncRobotsGate:
    """Enforce robots.txt rules and crawl-delay across a campaign."""

    def __init__(
        self,
        fetcher: Fetcher,
        *,
        user_agent: str = "*",
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._fetcher = fetcher
        self._user_agent = user_agent
        self._clock = clock
        self._sleep = sleep
        self._cache: dict[str, RobotFileParser | None] = {}
        self._next_allowed: dict[str, float] = {}

    async def _parser(self, url: str) -> RobotFileParser | None:
        split = urlsplit(url)
        origin = f"{split.scheme}://{split.netloc}"
        if origin not in self._cache:
            content = await self._fetcher(f"{origin}/robots.txt")
            if content is None:
                self._cache[origin] = None
            else:
                parser = RobotFileParser()
                parser.parse(content.splitlines())
                self._cache[origin] = parser
        return self._cache[origin]

    async def allowed(self, url: str) -> bool:
        parser = await self._parser(url)
        if parser is None:
            return True
        return parser.can_fetch(self._user_agent, url)

    async def throttle(self, url: str) -> None:
        parser = await self._parser(url)
        if parser is None:
            return
        delay = parser.crawl_delay(self._user_agent)
        if delay is None:
            return
        origin = "{0.scheme}://{0.netloc}".format(urlsplit(url))
        now = self._clock()
        earliest = self._next_allowed.get(origin, 0.0)
        wait = earliest - now
        if wait > 0:
            await self._sleep(wait)
            now = earliest
        self._next_allowed[origin] = now + float(delay)
