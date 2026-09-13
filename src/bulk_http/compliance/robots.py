"""robots.txt compliance: per-host fetch, cache, rules and crawl-delay.

Disabled by default at the engine level; enabled with a single option for use in
a legal framework. The fetcher is injected so the cache can be tested without any
network access.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

Fetcher = Callable[[str], str | None]


class RobotsCache:
    """Fetch and cache robots.txt per host, answering fetch and delay queries."""

    def __init__(self, fetcher: Fetcher, *, user_agent: str = "*") -> None:
        self._fetcher = fetcher
        self._user_agent = user_agent
        self._cache: dict[str, RobotFileParser | None] = {}

    def _parser_for(self, url: str) -> RobotFileParser | None:
        split = urlsplit(url)
        origin = f"{split.scheme}://{split.netloc}"
        if origin not in self._cache:
            content = self._fetcher(f"{origin}/robots.txt")
            if content is None:
                self._cache[origin] = None
            else:
                parser = RobotFileParser()
                parser.parse(content.splitlines())
                self._cache[origin] = parser
        return self._cache[origin]

    def can_fetch(self, url: str) -> bool:
        parser = self._parser_for(url)
        if parser is None:
            return True
        return parser.can_fetch(self._user_agent, url)

    def crawl_delay(self, url: str) -> float | None:
        parser = self._parser_for(url)
        if parser is None:
            return None
        delay = parser.crawl_delay(self._user_agent)
        return float(delay) if delay is not None else None
