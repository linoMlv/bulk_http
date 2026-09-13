"""The transport abstraction decoupling the engine from the native HTTP core."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from bulk_http.config import ResolvedRequest


@dataclass(frozen=True, slots=True, kw_only=True)
class RawResponse:
    """The low-level outcome of performing a single request.

    ``fragment`` holds the received body bytes as read off the wire (possibly
    truncated by Stream-Cut, possibly empty for Fast-Status). ``content_encoding``
    is the negotiated coding of that fragment. A transport-level failure sets
    ``error`` and leaves ``status`` as ``None``.
    """

    status: int | None
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    fragment: bytes = b""
    content_encoding: str | None = None
    truncated: bool = False
    elapsed: float | None = None
    error: str | None = None


@runtime_checkable
class Transport(Protocol):
    """Performs a single resolved request and returns a :class:`RawResponse`."""

    async def perform(self, resolved: ResolvedRequest) -> RawResponse: ...
