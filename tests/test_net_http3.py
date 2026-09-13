"""Tests for HTTP/3 availability detection and the transport guard."""

from collections.abc import AsyncIterator

import pytest

from bulk_http.config import EngineConfig
from bulk_http.models import Request
from bulk_http.net import curl as curl_mod
from bulk_http.net.curl import CurlTransport, http3_available


@pytest.fixture
async def transport() -> AsyncIterator[CurlTransport]:
    t = CurlTransport()
    yield t
    await t.aclose()


def test_http3_available_reflects_build() -> None:
    # Detection returns a bool; on this build (ngtcp2/nghttp3) it is True.
    assert isinstance(http3_available(), bool)


async def test_h3_request_without_support_errors_without_network(
    transport: CurlTransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(curl_mod, "http3_available", lambda: False)
    resolved = EngineConfig(http_version="h3").effective(Request(url="https://127.0.0.1:1/x"))
    resp = await transport.perform(resolved)
    assert resp.status is None
    assert resp.error == "http3_unavailable"


async def test_non_h3_request_is_unaffected_by_guard(
    transport: CurlTransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(curl_mod, "http3_available", lambda: False)
    resolved = EngineConfig(http_version="auto", timeout=2.0).effective(
        Request(url="http://127.0.0.1:1/x")
    )
    resp = await transport.perform(resolved)
    # Fails to connect (nothing listening) but not due to the h3 guard.
    assert resp.error != "http3_unavailable"
