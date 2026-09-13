"""Per-batch statistics, aggregated by the collector across workers."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from bulk_http.models import Result

_DEFAULT_SAMPLE_CAP = 256


@dataclass(frozen=True, slots=True)
class BatchStats:
    """Compact, picklable stats for one processed batch.

    Counts are exact; ``latencies`` is a bounded sample so the message stays small
    while still feeding percentile estimates when merged.
    """

    total: int = 0
    matched: int = 0
    by_status: dict[int, int] = field(default_factory=dict)
    errors: dict[str, int] = field(default_factory=dict)
    latencies: list[float] = field(default_factory=list)


def compute_batch_stats(
    results: list[Result], *, sample_cap: int = _DEFAULT_SAMPLE_CAP
) -> BatchStats:
    """Summarize a batch's results into a :class:`BatchStats`."""
    total = len(results)
    matched = 0
    by_status: Counter[int] = Counter()
    errors: Counter[str] = Counter()
    latencies: list[float] = []
    for result in results:
        if result.matched:
            matched += 1
        if result.status is not None:
            by_status[result.status] += 1
        if result.error is not None:
            errors[result.error] += 1
        if result.elapsed is not None and len(latencies) < sample_cap:
            latencies.append(result.elapsed)
    return BatchStats(
        total=total,
        matched=matched,
        by_status=dict(by_status),
        errors=dict(errors),
        latencies=latencies,
    )
