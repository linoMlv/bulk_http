"""Build a robots gate whose fetcher is backed by the worker's transport."""

from __future__ import annotations

from bulk_http.compliance import AsyncRobotsGate
from bulk_http.config import EngineConfig
from bulk_http.decompress import decompress_fragment
from bulk_http.models import Request
from bulk_http.net.transport import Transport


def make_robots_gate(config: EngineConfig, transport: Transport) -> AsyncRobotsGate | None:
    """Return a robots gate when ``respect_robots`` is set, else ``None``.

    The gate fetches robots.txt through the given transport (a full GET, so the
    body is read even under global fast-status/stream-cut defaults).
    """
    if not config.respect_robots:
        return None

    async def fetch(robots_url: str) -> str | None:
        resolved = config.effective(Request(url=robots_url, fast_status=False))
        response = await transport.perform(resolved)
        if response.status == 200:
            return decompress_fragment(response.fragment, response.content_encoding).decode(
                "utf-8", errors="replace"
            )
        return None

    return AsyncRobotsGate(fetch)
