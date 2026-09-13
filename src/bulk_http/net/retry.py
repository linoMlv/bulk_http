"""Method-aware retry policy with exponential backoff and jitter."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

from bulk_http.config import ResolvedRequest
from bulk_http.net.transport import RawResponse, Transport

Sleep = Callable[[float], Awaitable[None]]
Jitter = Callable[[], float]


def _is_transient(response: RawResponse) -> bool:
    """A transport failure or a 429 is worth retrying; other statuses are not."""
    return response.error is not None or response.status == 429


async def perform_with_retries(
    transport: Transport,
    resolved: ResolvedRequest,
    *,
    backoff_base: float = 0.2,
    backoff_cap: float = 10.0,
    sleep: Sleep = asyncio.sleep,
    jitter: Jitter = random.random,
) -> RawResponse:
    """Perform ``resolved`` through ``transport``, retrying transient failures.

    Transport errors and 429 responses are retried only for idempotent methods
    (or when ``retry_non_idempotent`` is set), up to ``resolved.retries`` extra
    attempts, with exponential backoff (capped) plus jitter. Other outcomes —
    including 4xx and 5xx statuses — are returned as-is.
    """
    replayable = resolved.is_idempotent or resolved.retry_non_idempotent
    last: RawResponse | None = None
    for attempt in range(resolved.retries + 1):
        response = await transport.perform(resolved)
        last = response
        if not _is_transient(response):
            return response
        if not replayable:
            return response
        if attempt == resolved.retries:
            return response
        delay = min(backoff_cap, backoff_base * (2**attempt)) + jitter() * backoff_base
        await sleep(delay)
    assert last is not None  # pragma: no cover - loop always returns
    return last  # pragma: no cover
