"""Tests for the local echo server test harness."""

import json
import urllib.request

from tests.support.echo_server import EchoServer


def _get(url: str) -> tuple[int, bytes, dict[str, str]]:
    with urllib.request.urlopen(url) as resp:
        return resp.status, resp.read(), dict(resp.headers)


def test_echo_server_starts_and_serves_default() -> None:
    with EchoServer() as server:
        status, body, _ = _get(server.url + "/")
        assert status == 200
        assert body == b"ok"


def test_status_route_returns_requested_code() -> None:
    with EchoServer() as server:
        req = urllib.request.Request(server.url + "/status/404")
        try:
            urllib.request.urlopen(req)
            raise AssertionError("expected HTTPError")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404


def test_bytes_route_returns_requested_size() -> None:
    with EchoServer() as server:
        status, body, headers = _get(server.url + "/bytes/2048")
        assert status == 200
        assert len(body) == 2048
        assert headers["Content-Length"] == "2048"


def test_headers_route_echoes_request_headers() -> None:
    with EchoServer() as server:
        req = urllib.request.Request(server.url + "/headers", headers={"X-Probe": "yes"})
        with urllib.request.urlopen(req) as resp:
            echoed = json.loads(resp.read())
        assert echoed.get("X-Probe") == "yes"


def test_url_is_localhost_with_port() -> None:
    with EchoServer() as server:
        assert server.url.startswith("http://127.0.0.1:")
