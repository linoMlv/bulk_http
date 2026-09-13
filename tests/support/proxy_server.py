"""A small fake HTTP proxy for network integration tests.

Test infrastructure only. In ``forward`` mode it relays absolute-URI GET requests
to their target using the stdlib client; in ``reject`` mode it answers every
request with a configured status code (e.g. 407) to exercise transport/proxy
error handling.
"""

from __future__ import annotations

import http.client
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from urllib.parse import urlsplit


def _make_handler(proxy: FakeProxy) -> type[BaseHTTPRequestHandler]:
    class _ProxyHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            proxy.request_count += 1
            if proxy.mode == "reject":
                self.send_response(proxy.code)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            target = urlsplit(self.path)
            conn = http.client.HTTPConnection(target.hostname or "", target.port or 80)
            path = target.path + (f"?{target.query}" if target.query else "")
            try:
                conn.request("GET", path or "/")
                upstream = conn.getresponse()
                body = upstream.read()
                self.send_response(upstream.status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            finally:
                conn.close()

    return _ProxyHandler


class FakeProxy:
    """A threaded fake proxy exposing a base ``url`` and a context manager."""

    def __init__(self, *, mode: str = "forward", code: int = 407, host: str = "127.0.0.1") -> None:
        self.mode = mode
        self.code = code
        self.request_count = 0
        self._server = ThreadingHTTPServer((host, 0), _make_handler(self))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        hostname = host.decode() if isinstance(host, bytes) else host
        return f"http://{hostname}:{port}"

    def start(self) -> FakeProxy:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def __enter__(self) -> FakeProxy:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop()
