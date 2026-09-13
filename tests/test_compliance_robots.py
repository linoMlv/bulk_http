"""Tests for robots.txt compliance with caching and crawl-delay."""

from bulk_http.compliance import RobotsCache

ROBOTS = "User-agent: *\nDisallow: /admin\nCrawl-delay: 2\n"


def test_disallowed_path_blocked() -> None:
    cache = RobotsCache(lambda url: ROBOTS)
    assert cache.can_fetch("https://a.com/admin/panel") is False
    assert cache.can_fetch("https://a.com/public") is True


def test_missing_robots_allows_all() -> None:
    cache = RobotsCache(lambda url: None)
    assert cache.can_fetch("https://a.com/admin") is True
    assert cache.crawl_delay("https://a.com/") is None


def test_crawl_delay_parsed() -> None:
    cache = RobotsCache(lambda url: ROBOTS)
    assert cache.crawl_delay("https://a.com/") == 2.0


def test_no_crawl_delay_returns_none() -> None:
    cache = RobotsCache(lambda url: "User-agent: *\nDisallow:\n")
    assert cache.crawl_delay("https://a.com/") is None


def test_robots_is_cached_per_host() -> None:
    calls: list[str] = []

    def fetcher(url: str) -> str:
        calls.append(url)
        return ROBOTS

    cache = RobotsCache(fetcher)
    cache.can_fetch("https://a.com/x")
    cache.can_fetch("https://a.com/y")
    cache.can_fetch("https://b.com/z")
    assert len(calls) == 2  # one fetch per host
    assert calls[0].endswith("/robots.txt")


def test_custom_user_agent() -> None:
    robots = "User-agent: BadBot\nDisallow: /\n\nUser-agent: *\nDisallow:\n"
    blocked = RobotsCache(lambda url: robots, user_agent="BadBot")
    allowed = RobotsCache(lambda url: robots, user_agent="GoodBot")
    assert blocked.can_fetch("https://a.com/x") is False
    assert allowed.can_fetch("https://a.com/x") is True
