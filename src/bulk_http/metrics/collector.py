"""Aggregate campaign metrics with a bounded memory footprint."""

from __future__ import annotations

import math
import random
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bulk_http.models import Result

Clock = Callable[[], float]


def _percentile(samples: list[float], pct: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    rank = math.ceil(pct / 100.0 * len(ordered))
    index = min(max(rank - 1, 0), len(ordered) - 1)
    return ordered[index]


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    """A point-in-time view of campaign metrics."""

    total: int
    matched: int
    by_status: dict[int, int]
    errors: dict[str, int]
    p50: float
    p95: float
    p99: float
    throughput: float
    elapsed_wall: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "matched": self.matched,
            "by_status": self.by_status,
            "errors": self.errors,
            "p50": self.p50,
            "p95": self.p95,
            "p99": self.p99,
            "throughput": self.throughput,
            "elapsed_wall": self.elapsed_wall,
        }


class MetricsCollector:
    """Accumulate result metrics; latencies use a bounded reservoir sample.

    Counts, status distribution and error types are exact; latency percentiles
    use reservoir sampling so memory stays bounded regardless of campaign size.
    """

    def __init__(
        self,
        *,
        reservoir_size: int = 10_000,
        clock: Clock = time.monotonic,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self._reservoir_size = reservoir_size
        self._clock = clock
        self._rng = rng
        self._start = clock()
        self._total = 0
        self._matched = 0
        self._by_status: Counter[int] = Counter()
        self._errors: Counter[str] = Counter()
        self._latencies: list[float] = []
        self._latency_seen = 0

    def record(self, result: Result) -> None:
        self._total += 1
        if result.matched:
            self._matched += 1
        if result.status is not None:
            self._by_status[result.status] += 1
        if result.error is not None:
            self._errors[result.error] += 1
        if result.elapsed is not None:
            self._sample_latency(result.elapsed)

    def _sample_latency(self, value: float) -> None:
        self._latency_seen += 1
        if len(self._latencies) < self._reservoir_size:
            self._latencies.append(value)
            return
        index = int(self._rng() * self._latency_seen)
        if index < self._reservoir_size:
            self._latencies[index] = value

    def snapshot(self) -> MetricsSnapshot:
        elapsed = self._clock() - self._start
        throughput = self._total / elapsed if elapsed > 0 else 0.0
        return MetricsSnapshot(
            total=self._total,
            matched=self._matched,
            by_status=dict(self._by_status),
            errors=dict(self._errors),
            p50=_percentile(self._latencies, 50),
            p95=_percentile(self._latencies, 95),
            p99=_percentile(self._latencies, 99),
            throughput=throughput,
            elapsed_wall=elapsed,
        )
