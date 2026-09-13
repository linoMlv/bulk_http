"""Group a lazy stream of items into bounded batches for IPC-efficient dispatch."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TypeVar

_T = TypeVar("_T")


def chunk_batches(items: Iterable[_T], size: int) -> Iterator[list[_T]]:
    """Yield lists of up to ``size`` items from ``items``, lazily.

    The final batch may be smaller. Batching amortizes inter-process transfer
    (never one task at a time) while keeping only one batch in memory at a time.
    """
    if size < 1:
        raise ValueError("size must be >= 1")
    batch: list[_T] = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch
