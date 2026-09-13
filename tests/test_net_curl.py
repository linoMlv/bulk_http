"""Integration tests for the curl_cffi transport against the local echo server."""

import gzip
from collections.abc import AsyncIterator

import pytest

from bulk_http.config import EngineConfig, ResolvedRequest
from bulk_http.models import Request
from bulk_http.net.curl import CurlTransport
from tests.support.echo_server import EchoServer


@pytest.fixture
async def transport() -> AsyncIterator[CurlTransport]:
    t = CurlTransport()
    yield t
    await t.aclose()


def _resolved(url: str, **overrides: object) -> ResolvedRequest:
    return EngineConfig().effective(Request(url=url, **overrides))  # type: ignore[arg-type]


async def test_simple_get_returns_status_and_body(transport: CurlTransport) -> None:
    with EchoServer() as server:
        resp = await transport.perform(_resolved(server.url + "/bytes/100"))
        assert resp.status == 200
        assert len(resp.fragment) == 100
        assert resp.error is None
        assert resp.elapsed is not None


async def test_compressed_body_kept_as_wire_bytes(transport: CurlTransport) -> None:
    with EchoServer() as server:
        resp = await transport.perform(_resolved(server.url + "/gzip?body=hello-secret"))
        assert resp.content_encoding == "gzip"
        # The fragment is the raw wire bytes, not decompressed by curl.
        assert gzip.decompress(resp.fragment) == b"hello-secret"


async def test_status_code_is_reported(transport: CurlTransport) -> None:
    with EchoServer() as server:
        resp = await transport.perform(_resolved(server.url + "/status/404"))
        assert resp.status == 404


async def test_transport_error_sets_error_and_no_status(transport: CurlTransport) -> None:
    resolved = EngineConfig(timeout=2.0).effective(Request(url="http://127.0.0.1:1/nope"))
    resp = await transport.perform(resolved)
    assert resp.status is None
    assert resp.error is not None


async def test_redirects_followed_when_enabled(transport: CurlTransport) -> None:
    with EchoServer() as server:
        resp = await transport.perform(
            EngineConfig(follow_redirects=True).effective(Request(url=server.url + "/redirect/2"))
        )
        assert resp.status == 200


async def test_redirects_not_followed_when_disabled(transport: CurlTransport) -> None:
    with EchoServer() as server:
        resp = await transport.perform(
            EngineConfig(follow_redirects=False).effective(Request(url=server.url + "/redirect/2"))
        )
        assert resp.status == 302


async def test_identity_accept_encoding_is_advertised() -> None:
    import json

    async with CurlTransport() as transport:
        with EchoServer() as server:
            resolved = EngineConfig(accept_encoding="identity").effective(
                Request(url=server.url + "/headers")
            )
            resp = await transport.perform(resolved)
            echoed = json.loads(resp.fragment)
            assert echoed["Accept-Encoding"] == "identity"


async def test_explicit_accept_encoding_header_is_respected() -> None:
    import json

    async with CurlTransport() as transport:
        with EchoServer() as server:
            resolved = EngineConfig().effective(
                Request(url=server.url + "/headers", headers={"Accept-Encoding": "gzip"})
            )
            resp = await transport.perform(resolved)
            echoed = json.loads(resp.fragment)
            assert echoed["Accept-Encoding"] == "gzip"


async def test_injected_session_is_not_closed_by_transport() -> None:
    from typing import Any

    from curl_cffi.requests import AsyncSession

    session: AsyncSession[Any] = AsyncSession()
    transport = CurlTransport(session=session)
    assert transport._owns_session is False
    await transport.aclose()  # must not close the injected session
    with EchoServer() as server:
        resolved = EngineConfig().effective(Request(url=server.url + "/"))
        resp = await transport.perform(resolved)
        assert resp.status == 200
    await session.close()
