"""Tests for the transport-backed robots gate builder."""

from bulk_http.config import EngineConfig, ResolvedRequest
from bulk_http.engine.robots_support import make_robots_gate
from bulk_http.net import FakeTransport, RawResponse


def test_no_gate_when_respect_robots_disabled() -> None:
    transport = FakeTransport.constant(RawResponse(status=200, url="u"))
    assert make_robots_gate(EngineConfig(), transport) is None


async def test_gate_allows_all_when_robots_missing() -> None:
    # robots.txt fetch returns 404 -> fetcher yields None -> allow everything.
    transport = FakeTransport.constant(RawResponse(status=404, url="u", fragment=b"nope"))
    gate = make_robots_gate(EngineConfig(respect_robots=True), transport)
    assert gate is not None
    assert await gate.allowed("https://a.com/anything") is True


async def test_gate_blocks_disallowed_when_robots_present() -> None:
    robots = b"User-agent: *\nDisallow: /secret\n"

    def responder(resolved: ResolvedRequest, attempt: int) -> RawResponse:
        return RawResponse(status=200, url=resolved.url, fragment=robots)

    gate = make_robots_gate(EngineConfig(respect_robots=True), FakeTransport(responder))
    assert gate is not None
    assert await gate.allowed("https://a.com/secret/x") is False
    assert await gate.allowed("https://a.com/ok") is True
