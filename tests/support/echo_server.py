"""A small, configurable local HTTP server for network integration tests.

This is test infrastructure, not part of the library's public API. It is a plain
stdlib server (so it does not depend on the networking core under test) that
mimics the response shapes real targets produce: status codes, sized bodies,
header echoing, content encodings, delays, redirects and unhealthy behaviors.
"""

from __future__ import annotations

import gzip
import json
import random
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from urllib.parse import parse_qs, urlsplit

import brotli
import zstandard


def _encode(coding: str, body: bytes) -> bytes:
    if coding == "gzip":
        return gzip.compress(body)
    if coding == "deflate":
        return zlib.compress(body)
    if coding == "br":
        return bytes(brotli.compress(body))
    if coding == "zstd":
        return zstandard.ZstdCompressor().compress(body)
    raise ValueError(coding)  # pragma: no cover


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: object) -> None:  # silence test noise
        pass

    def _send(
        self,
        code: int,
        body: bytes = b"",
        content_type: str = "text/plain",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self) -> None:
        split = urlsplit(self.path)
        parts = [p for p in split.path.split("/") if p]
        query = parse_qs(split.query)

        if not parts:
            self._send(200, b"ok")
            return
        head = parts[0]
        if head == "status" and len(parts) == 2 and parts[1].isdigit():
            self._send(int(parts[1]))
            return
        if head == "bytes" and len(parts) == 2 and parts[1].isdigit():
            self._send(200, b"x" * int(parts[1]), "application/octet-stream")
            return
        if head == "headers":
            received = dict(self.headers.items())
            self._send(200, json.dumps(received).encode(), "application/json")
            return
        if head in ("gzip", "deflate", "br", "zstd"):
            raw = query.get("body", ["ok"])[0].encode()
            self._send(
                200,
                _encode(head, raw),
                "application/octet-stream",
                {"Content-Encoding": head},
            )
            return
        if head == "html":
            title = query.get("title", ["Home"])[0]
            body = f"<html><head><title>{title}</title></head><body><p>hi</p></body></html>"
            self._send(200, body.encode(), "text/html; charset=utf-8")
            return
        if head == "json":
            self._send(200, json.dumps({"ok": True}).encode(), "application/json")
            return
        if head == "delay" and len(parts) == 2:
            time.sleep(float(parts[1]))
            self._send(200, b"ok")
            return
        if head == "redirect" and len(parts) == 2 and parts[1].isdigit():
            remaining = int(parts[1])
            if remaining <= 0:
                self._send(200, b"ok")
            else:
                self._send(302, b"", extra_headers={"Location": f"/redirect/{remaining - 1}"})
            return
        if head == "big":
            size = int(query.get("size", ["100000"])[0])
            coding = query.get("encoding", ["identity"])[0]
            # Poorly-compressible content so Stream-Cut actually truncates.
            rng = random.Random(1234)
            raw = b"MARKER" + rng.randbytes(max(0, size - 6))
            if coding == "identity":
                self._send(200, raw, "text/plain")
            else:
                self._send(
                    200,
                    _encode(coding, raw),
                    "application/octet-stream",
                    {"Content-Encoding": coding},
                )
            return
        if head == "head-405":
            self._send(200, b"ok")
            return
        if head == "drop":
            # Announce a body, then close the socket before sending it.
            self.send_response(200)
            self.send_header("Content-Length", "1000")
            self.end_headers()
            self.wfile.write(b"x" * 10)
            self.wfile.flush()
            self.connection.close()
            return
        if head == "slow":
            payload = query.get("body", ["ok"])[0].encode()
            chunks = int(query.get("chunks", ["2"])[0])
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            step = max(1, len(payload) // max(1, chunks))
            for start in range(0, len(payload), step):
                self.wfile.write(payload[start : start + step])
                self.wfile.flush()
                time.sleep(0.005)
            return
        self._send(404, b"not found")

    def do_HEAD(self) -> None:
        split = urlsplit(self.path)
        parts = [p for p in split.path.split("/") if p]
        if parts and parts[0] == "head-405":
            self._send(405)
            return
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


class EchoServer:
    """A threaded echo server exposing a base ``url`` and a context manager."""

    def __init__(self, host: str = "127.0.0.1") -> None:
        self._server = ThreadingHTTPServer((host, 0), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        hostname = host.decode() if isinstance(host, bytes) else host
        return f"http://{hostname}:{port}"

    def start(self) -> EchoServer:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def __enter__(self) -> EchoServer:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop()
