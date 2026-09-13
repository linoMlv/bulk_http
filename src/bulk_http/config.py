"""Engine configuration: global defaults and per-request override resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from bulk_http._types import (
    ACCEPT_ENCODINGS,
    CUT_ON_VALUES,
    HTTP_VERSIONS,
    AcceptEncoding,
    CutOn,
    HttpVersion,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class EngineConfig:
    """Global engine defaults.

    Every field here is the fallback value used when a :class:`~bulk_http.models.Request`
    leaves the corresponding override unset. The config is plain data and stays
    picklable so it can be shipped once to each spawned worker.
    """

    # Concurrency and hardware.
    workers: int | Literal["auto"] = "auto"
    concurrency_per_worker: int = 450
    chunk_size: int = 1000
    max_tasks_per_child: int | None = 50_000
    in_flight_batches: int = 4

    # Network and protocol.
    stream_cut: int | None = None
    cut_on: CutOn = "wire"
    fast_status: bool = False
    accept_encoding: AcceptEncoding = "impersonate"
    http_version: HttpVersion = "auto"
    verify_ssl: bool = True
    follow_redirects: bool = False
    max_redirects: int = 10
    timeout: float = 30.0
    total_timeout: float | None = None
    retries: int = 2
    retry_non_idempotent: bool = False

    # Anti-detection.
    impersonate: str = "chrome"

    # Compliance guardrails.
    respect_robots: bool = False
    per_domain_rate_limit: float | None = None

    # Persistence.
    checkpoint: str | None = None

    def __post_init__(self) -> None:
        if self.workers != "auto" and (not isinstance(self.workers, int) or self.workers < 1):
            raise ValueError('workers must be a positive int or "auto"')
        if self.concurrency_per_worker < 1:
            raise ValueError("concurrency_per_worker must be >= 1")
        if self.chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        if self.in_flight_batches < 1:
            raise ValueError("in_flight_batches must be >= 1")
        if self.max_tasks_per_child is not None and self.max_tasks_per_child < 1:
            raise ValueError("max_tasks_per_child must be >= 1 or None")
        if self.stream_cut is not None and self.stream_cut <= 0:
            raise ValueError("stream_cut must be a positive number of bytes or None")
        if self.cut_on not in CUT_ON_VALUES:
            raise ValueError(f"invalid cut_on: {self.cut_on!r}")
        if self.http_version not in HTTP_VERSIONS:
            raise ValueError(f"invalid http_version: {self.http_version!r}")
        if self.accept_encoding not in ACCEPT_ENCODINGS:
            raise ValueError(f"invalid accept_encoding: {self.accept_encoding!r}")
        if self.max_redirects < 0:
            raise ValueError("max_redirects must be >= 0")
        if self.timeout <= 0:
            raise ValueError("timeout must be > 0")
        if self.total_timeout is not None and self.total_timeout <= 0:
            raise ValueError("total_timeout must be > 0 or None")
        if self.retries < 0:
            raise ValueError("retries must be >= 0")
        if self.per_domain_rate_limit is not None and self.per_domain_rate_limit <= 0:
            raise ValueError("per_domain_rate_limit must be > 0 or None")
