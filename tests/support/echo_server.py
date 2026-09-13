"""A small, configurable local HTTP server for network integration tests.

This is test infrastructure, not part of the library's public API. It is a plain
stdlib server (so it does not depend on the networking core under test) that
mimics the response shapes real targets produce: status codes, sized bodies,
header echoing, and — added incrementally — encodings, delays, redirects and
unhealthy behaviors.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: object) -> None:  # silence test noise
        pass

    def _send(self, code: int, body: bytes = b"", content_type: str = "text/plain") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        parts = [p for p in path.split("/") if p]

        if not parts:
            self._send(200, b"ok")
            return
        if parts[0] == "status" and len(parts) == 2 and parts[1].isdigit():
            self._send(int(parts[1]))
            return
        if parts[0] == "bytes" and len(parts) == 2 and parts[1].isdigit():
            self._send(200, b"x" * int(parts[1]), "application/octet-stream")
            return
        if parts[0] == "headers":
            received = dict(self.headers.items())
            self._send(200, json.dumps(received).encode(), "application/json")
            return
        self._send(404, b"not found")


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
