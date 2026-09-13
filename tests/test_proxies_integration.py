"""Integration: routing a curl request through the fake proxy."""

from collections.abc import AsyncIterator

import pytest

from bulk_http.config import EngineConfig
from bulk_http.models import Request
from bulk_http.net.curl import CurlTransport
from bulk_http.proxies import classify_outcome
from tests.support.echo_server import EchoServer
from tests.support.proxy_server import FakeProxy


@pytest.fixture
async def transport() -> AsyncIterator[CurlTransport]:
    t = CurlTransport()
    yield t
    await t.aclose()


async def test_request_is_routed_through_proxy(transport: CurlTransport) -> None:
    with EchoServer() as server, FakeProxy(mode="forward") as proxy:
        resolved = EngineConfig().effective(Request(url=server.url + "/bytes/64", proxy=proxy.url))
        resp = await transport.perform(resolved)
        assert resp.status == 200
        assert len(resp.fragment) == 64
        assert proxy.request_count >= 1


async def test_proxy_407_is_classified_as_transport_error(transport: CurlTransport) -> None:
    with EchoServer() as server, FakeProxy(mode="reject", code=407) as proxy:
        resolved = EngineConfig().effective(Request(url=server.url + "/", proxy=proxy.url))
        resp = await transport.perform(resolved)
        assert classify_outcome(resp) == "transport_error"
