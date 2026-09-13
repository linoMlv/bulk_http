"""The control message a worker returns after committing one batch."""

from __future__ import annotations

from dataclasses import dataclass, field

from bulk_http.metrics import BatchStats


@dataclass(frozen=True, slots=True)
class ControlMessage:
    """Reports a durably-committed batch: its worker file, offset, count and stats.

    One message per batch (never per request) is sent back to the coordinator,
    which advances the checkpoint after the worker's output is flushed and synced
    and folds the batch statistics into the campaign metrics.
    """

    chunk_id: int
    worker_file: str
    offset: int
    count: int
    stats: BatchStats = field(default_factory=BatchStats)
