"""Tests for the fake proxy test harness."""

import urllib.error
import urllib.request

import pytest

from tests.support.echo_server import EchoServer
from tests.support.proxy_server import FakeProxy


def _get_via_proxy(url: str, proxy_url: str) -> tuple[int, bytes]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy_url}))
    with opener.open(url) as resp:
        return resp.status, resp.read()


def test_forward_proxy_relays_to_target() -> None:
    with EchoServer() as server, FakeProxy(mode="forward") as proxy:
        status, body = _get_via_proxy(server.url + "/bytes/128", proxy.url)
        assert status == 200
        assert len(body) == 128
        assert proxy.request_count >= 1


def test_reject_proxy_returns_configured_code() -> None:
    with EchoServer() as server, FakeProxy(mode="reject", code=407) as proxy:
        with pytest.raises(urllib.error.HTTPError) as exc:
            _get_via_proxy(server.url + "/", proxy.url)
        assert exc.value.code == 407


def test_proxy_url_is_localhost() -> None:
    with FakeProxy(mode="forward") as proxy:
        assert proxy.url.startswith("http://127.0.0.1:")
