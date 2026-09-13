"""Concurrency and multiprocess distribution."""

from __future__ import annotations

from bulk_http.concurrency.chunking import chunk_batches
from bulk_http.concurrency.pool import WorkerPool
from bulk_http.concurrency.processor import TaskProcessor
from bulk_http.concurrency.sizing import (
    choose_loop,
    compute_workers,
    effective_concurrency,
    resolve_workers,
    run,
)

__all__ = [
    "TaskProcessor",
    "WorkerPool",
    "choose_loop",
    "chunk_batches",
    "compute_workers",
    "effective_concurrency",
    "resolve_workers",
    "run",
]
