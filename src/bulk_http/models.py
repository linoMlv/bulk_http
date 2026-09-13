"""Core data models: the per-request specification carried through the engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bulk_http._types import (
    ACCEPT_ENCODINGS,
    CTX_TYPES,
    CUT_ON_VALUES,
    HTTP_VERSIONS,
    METHODS,
    AcceptEncoding,
    CtxType,
    CutOn,
    HttpVersion,
    Method,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Request:
    """A single HTTP request specification.

    ``url`` is mandatory. Data fields (headers, cookies, body, needles,
    ``expected_status``, ``meta``) describe the request itself. Every network
    field is optional and defaults to ``None``, meaning "inherit the engine's
    global default"; resolution happens later against an ``EngineConfig``.
    """

    url: str
    method: Method = "GET"

    # Request data.
    headers: dict[str, str] | None = None
    cookies: dict[str, str] | None = None
    body: bytes | None = None
    needles: tuple[str, ...] = ()
    expected_status: int | frozenset[int] | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    # Network overrides (None -> inherit the engine default).
    proxy: str | None = None
    stream_cut: int | None = None
    cut_on: CutOn | None = None
    fast_status: bool | None = None
    follow_redirects: bool | None = None
    max_redirects: int | None = None
    verify_ssl: bool | None = None
    impersonate: str | None = None
    http_version: HttpVersion | None = None
    accept_encoding: AcceptEncoding | None = None
    timeout: float | None = None
    total_timeout: float | None = None
    retries: int | None = None
    retry_non_idempotent: bool | None = None

    def __post_init__(self) -> None:
        if not self.url:
            raise ValueError("Request.url must be a non-empty string")
        if self.method not in METHODS:
            raise ValueError(f"unknown HTTP method: {self.method!r}")
        if self.cut_on is not None and self.cut_on not in CUT_ON_VALUES:
            raise ValueError(f"invalid cut_on: {self.cut_on!r}")
        if self.http_version is not None and self.http_version not in HTTP_VERSIONS:
            raise ValueError(f"invalid http_version: {self.http_version!r}")
        if self.accept_encoding is not None and self.accept_encoding not in ACCEPT_ENCODINGS:
            raise ValueError(f"invalid accept_encoding: {self.accept_encoding!r}")
        if self.stream_cut is not None and self.stream_cut <= 0:
            raise ValueError("stream_cut must be a positive number of bytes")
        if self.max_redirects is not None and self.max_redirects < 0:
            raise ValueError("max_redirects must be >= 0")
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError("timeout must be > 0")
        if self.total_timeout is not None and self.total_timeout <= 0:
            raise ValueError("total_timeout must be > 0")
        if self.retries is not None and self.retries < 0:
            raise ValueError("retries must be >= 0")


@dataclass(frozen=True, slots=True, kw_only=True)
class Task:
    """A request paired with its source-line identity.

    ``source_id`` is the idempotency key (the position of the row in the input
    source). Tasks are the units distributed to worker processes, so they must
    remain picklable under the ``spawn`` start method.
    """

    source_id: int
    request: Request

    def __post_init__(self) -> None:
        if self.source_id < 0:
            raise ValueError("source_id must be >= 0")


@dataclass(frozen=True, slots=True, kw_only=True)
class Result:
    """A standardized output record for a validated (or failed) request."""

    source_id: int
    url: str
    status: int | None
    matched: bool
    data: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    elapsed: float | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class EvalContext:
    """The context object passed to a user predicate.

    ``type`` selects which payload field is populated: ``data`` for JSON
    (deserialized), ``dom`` for HTML (a parsed tree), ``text`` for anything
    else. ``raw`` always holds the received (decompressed) fragment.
    """

    type: CtxType
    status: int
    url: str
    headers: dict[str, str]
    meta: dict[str, Any]
    raw: bytes
    data: Any | None = None
    dom: Any | None = None
    text: str | None = None

    def __post_init__(self) -> None:
        if self.type not in CTX_TYPES:
            raise ValueError(f"invalid context type: {self.type!r}")
