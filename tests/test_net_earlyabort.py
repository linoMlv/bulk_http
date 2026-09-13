"""Integration tests for Fast-Status and Stream-Cut early network abort."""

from collections.abc import AsyncIterator

import pytest

from bulk_http.config import EngineConfig
from bulk_http.decompress import decompress_fragment
from bulk_http.models import Request
from bulk_http.net.curl import CurlTransport
from tests.support.echo_server import EchoServer


@pytest.fixture
async def transport() -> AsyncIterator[CurlTransport]:
    t = CurlTransport()
    yield t
    await t.aclose()


async def test_fast_status_returns_status_without_body(transport: CurlTransport) -> None:
    with EchoServer() as server:
        resolved = EngineConfig(fast_status=True).effective(
            Request(url=server.url + "/bytes/500000")
        )
        resp = await transport.perform(resolved)
        assert resp.status == 200
        assert resp.fragment == b""
        assert resp.truncated is True


async def test_stream_cut_wire_stops_early(transport: CurlTransport) -> None:
    with EchoServer() as server:
        resolved = EngineConfig(stream_cut=2000).effective(
            Request(url=server.url + "/bytes/500000")
        )
        resp = await transport.perform(resolved)
        assert resp.status == 200
        assert resp.truncated is True
        assert 0 < len(resp.fragment) < 500000


async def test_stream_cut_below_threshold_reads_all(transport: CurlTransport) -> None:
    with EchoServer() as server:
        resolved = EngineConfig(stream_cut=10000).effective(Request(url=server.url + "/bytes/100"))
        resp = await transport.perform(resolved)
        assert len(resp.fragment) == 100
        assert resp.truncated is False


async def test_stream_cut_wire_on_compressed_yields_decodable_prefix(
    transport: CurlTransport,
) -> None:
    with EchoServer() as server:
        resolved = EngineConfig(stream_cut=1500).effective(
            Request(url=server.url + "/big?size=200000&encoding=gzip")
        )
        resp = await transport.perform(resolved)
        assert resp.content_encoding == "gzip"
        decoded = decompress_fragment(resp.fragment, "gzip")
        assert decoded.startswith(b"MARKER")
        assert len(decoded) > 0
        assert resp.truncated is True


async def test_stream_cut_decoded_counts_decompressed_bytes(
    transport: CurlTransport,
) -> None:
    with EchoServer() as server:
        resolved = EngineConfig(stream_cut=5000, cut_on="decoded").effective(
            Request(url=server.url + "/big?size=200000&encoding=gzip")
        )
        resp = await transport.perform(resolved)
        decoded = decompress_fragment(resp.fragment, "gzip")
        assert len(decoded) >= 5000
        assert resp.truncated is True


async def test_early_abort_is_stable_under_mixed_load(transport: CurlTransport) -> None:
    # Exercise the abort path repeatedly on healthy and unhealthy connections to
    # guard against the historical segfault on closing an interrupted stream.
    with EchoServer() as server:
        paths = ["/bytes/300000", "/slow?body=hello&chunks=8", "/drop", "/head-405"]
        for i in range(24):
            path = paths[i % len(paths)]
            fast = i % 2 == 0
            cfg = EngineConfig(fast_status=fast, stream_cut=None if fast else 1000, timeout=3.0)
            resp = await transport.perform(cfg.effective(Request(url=server.url + path)))
            # Must always return a RawResponse (never crash), error or not.
            assert resp.status is not None or resp.error is not None
