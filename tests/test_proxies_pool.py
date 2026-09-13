"""Tests for the health-aware proxy pool and its file source."""

from pathlib import Path

from bulk_http import sources
from bulk_http.proxies import ProxyPool


def test_pool_round_robins_over_healthy_proxies() -> None:
    pool = ProxyPool(["http://p1:1", "http://p2:2", "http://p3:3"])
    picks = [pool.select(now=0.0) for _ in range(6)]
    assert picks == [
        "http://p1:1",
        "http://p2:2",
        "http://p3:3",
        "http://p1:1",
        "http://p2:2",
        "http://p3:3",
    ]


def test_pool_returns_none_when_empty() -> None:
    assert ProxyPool([]).select(now=0.0) is None


def test_pool_skips_quarantined_proxy() -> None:
    pool = ProxyPool(
        ["http://p1:1", "http://p2:2"],
        window=10,
        failure_threshold=0.5,
        min_samples=4,
        cooldown=60.0,
    )
    for _ in range(4):
        pool.report("http://p1:1", "transport_error", now=1.0)
    picks = {pool.select(now=1.0) for _ in range(4)}
    assert picks == {"http://p2:2"}


def test_pool_returns_none_when_all_quarantined() -> None:
    pool = ProxyPool(["http://p1:1"], min_samples=2, failure_threshold=0.5, cooldown=30.0)
    pool.report("http://p1:1", "transport_error", now=1.0)
    pool.report("http://p1:1", "transport_error", now=1.0)
    assert pool.select(now=1.0) is None
    assert pool.select(now=1.0 + 31.0) == "http://p1:1"


def test_pool_report_ignores_unknown_proxy() -> None:
    pool = ProxyPool(["http://p1:1"])
    pool.report("http://unknown:9", "transport_error", now=1.0)  # must not raise
    assert pool.select(now=1.0) == "http://p1:1"


def test_proxy_pool_source_reads_file(tmp_path: Path) -> None:
    p = tmp_path / "proxies.txt"
    p.write_text("http://p1:1\n\nhttp://p2:2\n  \n")
    assert sources.proxy_pool(p) == ["http://p1:1", "http://p2:2"]
