"""Engine configuration: global defaults and per-request override resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from bulk_http._types import (
    ACCEPT_ENCODINGS,
    CUT_ON_VALUES,
    HTTP_VERSIONS,
    IDEMPOTENT_METHODS,
    AcceptEncoding,
    CutOn,
    HttpVersion,
    Method,
)
from bulk_http.models import Request


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolvedRequest:
    """A request with every network field resolved to a concrete value.

    Produced by :meth:`EngineConfig.effective`, combining a :class:`Request`'s
    overrides with the engine's global defaults. ``stream_cut`` stays ``None``
    when unlimited.
    """

    url: str
    method: Method
    headers: dict[str, str] | None
    cookies: dict[str, str] | None
    body: bytes | None
    needles: tuple[str, ...]
    expected_status: int | frozenset[int] | None
    meta: dict[str, Any]

    proxy: str | None
    stream_cut: int | None
    cut_on: CutOn
    fast_status: bool
    follow_redirects: bool
    max_redirects: int
    verify_ssl: bool
    impersonate: str
    http_version: HttpVersion
    accept_encoding: AcceptEncoding
    timeout: float
    total_timeout: float | None
    retries: int
    retry_non_idempotent: bool

    @property
    def is_idempotent(self) -> bool:
        return self.method in IDEMPOTENT_METHODS


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
    allowlist: tuple[str, ...] = ()
    denylist: tuple[str, ...] = ()
    identity_header: tuple[str, str] | None = None
    authorization: str | None = None

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

    def effective(self, request: Request) -> ResolvedRequest:
        """Resolve ``request``'s overrides against these global defaults."""
        r = request
        return ResolvedRequest(
            url=r.url,
            method=r.method,
            headers=r.headers,
            cookies=r.cookies,
            body=r.body,
            needles=r.needles,
            expected_status=r.expected_status,
            meta=r.meta,
            proxy=r.proxy,
            stream_cut=r.stream_cut if r.stream_cut is not None else self.stream_cut,
            cut_on=r.cut_on if r.cut_on is not None else self.cut_on,
            fast_status=r.fast_status if r.fast_status is not None else self.fast_status,
            follow_redirects=(
                r.follow_redirects if r.follow_redirects is not None else self.follow_redirects
            ),
            max_redirects=r.max_redirects if r.max_redirects is not None else self.max_redirects,
            verify_ssl=r.verify_ssl if r.verify_ssl is not None else self.verify_ssl,
            impersonate=r.impersonate if r.impersonate is not None else self.impersonate,
            http_version=r.http_version if r.http_version is not None else self.http_version,
            accept_encoding=(
                r.accept_encoding if r.accept_encoding is not None else self.accept_encoding
            ),
            timeout=r.timeout if r.timeout is not None else self.timeout,
            total_timeout=(r.total_timeout if r.total_timeout is not None else self.total_timeout),
            retries=r.retries if r.retries is not None else self.retries,
            retry_non_idempotent=(
                r.retry_non_idempotent
                if r.retry_non_idempotent is not None
                else self.retry_non_idempotent
            ),
        )
