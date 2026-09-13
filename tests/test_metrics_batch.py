"""Tests for batch statistics and their aggregation into the collector."""

from bulk_http.metrics import BatchStats, MetricsCollector, compute_batch_stats
from bulk_http.models import Result


def _r(
    sid: int,
    status: int | None,
    matched: bool,
    elapsed: float | None = 0.1,
    error: str | None = None,
) -> Result:
    return Result(
        source_id=sid, url="u", status=status, matched=matched, elapsed=elapsed, error=error
    )


def test_compute_batch_stats() -> None:
    stats = compute_batch_stats(
        [
            _r(0, 200, True),
            _r(1, 200, False),
            _r(2, 404, False),
            _r(3, None, False, elapsed=None, error="timeout"),
        ]
    )
    assert stats.total == 4
    assert stats.matched == 1
    assert stats.by_status == {200: 2, 404: 1}
    assert stats.errors == {"timeout": 1}
    assert len(stats.latencies) == 3  # three results carried a latency


def test_empty_batch_stats_default() -> None:
    stats = BatchStats()
    assert stats.total == 0
    assert stats.by_status == {}


def test_collector_merges_batch_stats() -> None:
    collector = MetricsCollector()
    collector.merge(compute_batch_stats([_r(0, 200, True, elapsed=1.0)]))
    collector.merge(compute_batch_stats([_r(1, 404, False, elapsed=3.0)]))
    snap = collector.snapshot()
    assert snap.total == 2
    assert snap.matched == 1
    assert snap.by_status == {200: 1, 404: 1}
    assert snap.p50 in (1.0, 3.0)


def test_batch_stats_latency_sample_is_bounded() -> None:
    stats = compute_batch_stats(
        [_r(i, 200, True, elapsed=float(i)) for i in range(1000)], sample_cap=100
    )
    assert len(stats.latencies) == 100


def test_collector_merge_aggregates_errors() -> None:
    collector = MetricsCollector()
    collector.merge(compute_batch_stats([_r(0, None, False, elapsed=None, error="timeout")]))
    collector.merge(compute_batch_stats([_r(1, None, False, elapsed=None, error="timeout")]))
    snap = collector.snapshot()
    assert snap.errors == {"timeout": 2}
