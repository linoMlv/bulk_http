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


def _get_raw(url: str) -> tuple[int, bytes, dict[str, str]]:
    req = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
    with urllib.request.urlopen(req) as resp:
        return resp.status, resp.read(), dict(resp.headers)


def test_gzip_route_sets_encoding_and_compresses() -> None:
    import gzip

    with EchoServer() as server:
        status, body, headers = _get_raw(server.url + "/gzip?body=hello-world")
        assert status == 200
        assert headers["Content-Encoding"] == "gzip"
        assert gzip.decompress(body) == b"hello-world"


def test_deflate_route() -> None:
    import zlib

    with EchoServer() as server:
        _, body, headers = _get_raw(server.url + "/deflate?body=abc")
        assert headers["Content-Encoding"] == "deflate"
        assert zlib.decompress(body) == b"abc"


def test_brotli_route() -> None:
    import brotli

    with EchoServer() as server:
        _, body, headers = _get_raw(server.url + "/br?body=xyz")
        assert headers["Content-Encoding"] == "br"
        assert brotli.decompress(body) == b"xyz"


def test_zstd_route() -> None:
    import zstandard

    with EchoServer() as server:
        _, body, headers = _get_raw(server.url + "/zstd?body=data")
        assert headers["Content-Encoding"] == "zstd"
        assert zstandard.ZstdDecompressor().decompress(body) == b"data"


def test_html_route_has_title_and_content_type() -> None:
    with EchoServer() as server:
        _, body, headers = _get_raw(server.url + "/html?title=Welcome")
        assert "text/html" in headers["Content-Type"]
        assert b"<title>Welcome</title>" in body


def test_json_route() -> None:
    with EchoServer() as server:
        _, body, headers = _get_raw(server.url + "/json")
        assert "application/json" in headers["Content-Type"]
        assert json.loads(body) == {"ok": True}


def test_redirect_route_chains_to_final_ok() -> None:
    with EchoServer() as server, urllib.request.urlopen(server.url + "/redirect/3") as resp:
        assert resp.status == 200
        assert resp.read() == b"ok"


def test_delay_route_waits() -> None:
    import time

    with EchoServer() as server:
        start = time.monotonic()
        _get(server.url + "/delay/0")
        assert time.monotonic() - start < 2.0
