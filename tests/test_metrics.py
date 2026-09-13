"""Tests for the metrics collector."""

from bulk_http.metrics import MetricsCollector
from bulk_http.models import Result


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def time(self) -> float:
        return self.t


def _result(
    sid: int,
    status: int | None,
    matched: bool,
    elapsed: float | None = 0.1,
    error: str | None = None,
) -> Result:
    return Result(
        source_id=sid, url="u", status=status, matched=matched, elapsed=elapsed, error=error
    )


def test_counts_total_and_matched() -> None:
    m = MetricsCollector()
    m.record(_result(0, 200, True))
    m.record(_result(1, 200, False))
    snap = m.snapshot()
    assert snap.total == 2
    assert snap.matched == 1


def test_status_distribution() -> None:
    m = MetricsCollector()
    m.record(_result(0, 200, True))
    m.record(_result(1, 200, True))
    m.record(_result(2, 404, False))
    snap = m.snapshot()
    assert snap.by_status == {200: 2, 404: 1}


def test_error_counts_by_type() -> None:
    m = MetricsCollector()
    m.record(_result(0, None, False, elapsed=None, error="ConnectTimeout"))
    m.record(_result(1, None, False, elapsed=None, error="ConnectTimeout"))
    m.record(_result(2, None, False, elapsed=None, error="DNSError"))
    snap = m.snapshot()
    assert snap.errors == {"ConnectTimeout": 2, "DNSError": 1}


def test_latency_percentiles() -> None:
    m = MetricsCollector()
    for i in range(1, 101):
        m.record(_result(i, 200, True, elapsed=float(i)))
    snap = m.snapshot()
    assert snap.p50 == 50.0
    assert snap.p95 == 95.0
    assert snap.p99 == 99.0


def test_throughput_uses_wall_clock() -> None:
    clock = FakeClock()
    m = MetricsCollector(clock=clock.time)
    for i in range(10):
        m.record(_result(i, 200, True))
    clock.t = 5.0
    snap = m.snapshot()
    assert snap.throughput == 2.0  # 10 results / 5 seconds


def test_snapshot_as_dict_is_serializable() -> None:
    m = MetricsCollector()
    m.record(_result(0, 200, True))
    d = m.snapshot().as_dict()
    assert d["total"] == 1
    assert "p95" in d


def test_no_latency_samples_yields_zero_percentiles() -> None:
    m = MetricsCollector()
    m.record(_result(0, None, False, elapsed=None, error="X"))
    snap = m.snapshot()
    assert snap.p50 == 0.0
    assert snap.p95 == 0.0


def test_empty_snapshot_has_zero_throughput() -> None:
    clock = FakeClock()
    m = MetricsCollector(clock=clock.time)
    assert m.snapshot().throughput == 0.0


def test_reservoir_sampling_bounds_memory() -> None:
    # A tiny reservoir with rng=0.0 always replaces index 0 once full.
    m = MetricsCollector(reservoir_size=3, rng=lambda: 0.0)
    for i in range(1, 11):
        m.record(_result(i, 200, True, elapsed=float(i)))
    # Only 3 latency samples are retained regardless of the 10 recorded.
    assert len(m._latencies) == 3


def test_reservoir_skips_replacement_when_index_out_of_range() -> None:
    # rng=0.99 -> index near latency_seen, beyond the reservoir -> no replacement.
    m = MetricsCollector(reservoir_size=2, rng=lambda: 0.99)
    for i in range(1, 21):
        m.record(_result(i, 200, True, elapsed=float(i)))
    assert len(m._latencies) == 2
