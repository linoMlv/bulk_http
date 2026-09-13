"""The production transport backed by curl_cffi (libcurl-impersonate)."""

from __future__ import annotations

import time
from functools import lru_cache
from types import TracebackType
from typing import Any

from curl_cffi import Curl, CurlError
from curl_cffi.const import CurlHttpVersion
from curl_cffi.requests import AsyncSession

from bulk_http._types import HttpVersion
from bulk_http.config import ResolvedRequest
from bulk_http.decompress import decompress_fragment
from bulk_http.net.transport import RawResponse

# A browser-consistent Accept-Encoding advertised to targets. curl's own
# auto-decompression is disabled (see below) so fragments arrive as wire bytes.
_IMPERSONATE_ACCEPT_ENCODING = "gzip, deflate, br, zstd"

_HTTP_VERSION_MAP: dict[HttpVersion, CurlHttpVersion | None] = {
    "auto": None,
    "h1": CurlHttpVersion.V1_1,
    "h2": CurlHttpVersion.V2_0,
    "h3": CurlHttpVersion.V3,
}


@lru_cache(maxsize=1)
def http3_available() -> bool:
    """Whether this libcurl build supports HTTP/3 (QUIC).

    Detected from the libcurl version string; HTTP/3 needs a QUIC backend
    (ngtcp2/nghttp3 or quiche) compiled in. Note that even when available, h3
    proxying requires a UDP-capable proxy (SOCKS5 UDP ASSOCIATE), rarely offered
    by residential pools.
    """
    try:
        raw = Curl().version()
    except Exception:  # pragma: no cover - defensive
        return False
    text = raw.decode() if isinstance(raw, bytes) else str(raw)
    return any(token in text for token in ("nghttp3", "ngtcp2", "quiche"))


class CurlTransport:
    """Perform requests with curl_cffi, keeping fingerprint impersonation.

    curl's automatic decompression is disabled (``accept_encoding=None``) so the
    fragment is the raw wire body; the advertised ``Accept-Encoding`` is set
    explicitly to stay consistent with the impersonated profile. Decompression is
    handled downstream, which is what makes Stream-Cut's wire semantics possible.

    Fast-Status aborts before reading any body; Stream-Cut reads until a byte
    threshold (measured on the wire, or on the decoded content) and then aborts.
    Both use a single, carefully-closed streaming path to avoid the historical
    segfault on tearing down an interrupted response.
    """

    def __init__(self, session: AsyncSession[Any] | None = None) -> None:
        self._session = session if session is not None else AsyncSession()
        self._owns_session = session is None

    def _headers_for(self, resolved: ResolvedRequest) -> dict[str, str]:
        headers = dict(resolved.headers or {})
        if not any(key.lower() == "accept-encoding" for key in headers):
            if resolved.accept_encoding == "identity":
                headers["Accept-Encoding"] = "identity"
            else:
                headers["Accept-Encoding"] = _IMPERSONATE_ACCEPT_ENCODING
        return headers

    async def _request(self, resolved: ResolvedRequest, *, stream: bool) -> Any:
        return await self._session.request(
            resolved.method,
            resolved.url,
            headers=self._headers_for(resolved),
            cookies=resolved.cookies,
            content=resolved.body,
            proxy=resolved.proxy,
            timeout=resolved.timeout,
            verify=resolved.verify_ssl,
            impersonate=resolved.impersonate,  # type: ignore[arg-type]
            accept_encoding=None,
            allow_redirects=resolved.follow_redirects,
            max_redirects=resolved.max_redirects,
            http_version=_HTTP_VERSION_MAP[resolved.http_version],
            stream=stream,
        )

    async def perform(self, resolved: ResolvedRequest) -> RawResponse:
        start = time.monotonic()
        if resolved.http_version == "h3" and not http3_available():
            return RawResponse(
                status=None,
                url=resolved.url,
                error="http3_unavailable",
                elapsed=time.monotonic() - start,
            )
        try:
            if resolved.fast_status:
                return await self._perform_fast_status(resolved, start)
            if resolved.stream_cut is not None:
                return await self._perform_stream_cut(resolved, start)
            return await self._perform_full(resolved, start)
        except CurlError as error:
            return RawResponse(
                status=None,
                url=resolved.url,
                error=type(error).__name__,
                elapsed=time.monotonic() - start,
            )

    async def _perform_full(self, resolved: ResolvedRequest, start: float) -> RawResponse:
        response = await self._request(resolved, stream=False)
        return RawResponse(
            status=response.status_code,
            url=str(response.url),
            headers=dict(response.headers),
            fragment=response.content,
            content_encoding=response.headers.get("Content-Encoding"),
            elapsed=time.monotonic() - start,
        )

    async def _perform_fast_status(self, resolved: ResolvedRequest, start: float) -> RawResponse:
        response = await self._request(resolved, stream=True)
        try:
            return RawResponse(
                status=response.status_code,
                url=str(response.url),
                headers=dict(response.headers),
                fragment=b"",
                content_encoding=response.headers.get("Content-Encoding"),
                truncated=True,
                elapsed=time.monotonic() - start,
            )
        finally:
            await response.aclose()

    async def _perform_stream_cut(self, resolved: ResolvedRequest, start: float) -> RawResponse:
        threshold = resolved.stream_cut
        assert threshold is not None
        response = await self._request(resolved, stream=True)
        content_encoding = response.headers.get("Content-Encoding")
        buffer = bytearray()
        truncated = False
        try:
            async for chunk in response.aiter_content():
                buffer += chunk
                if resolved.cut_on == "decoded":
                    reached = len(decompress_fragment(bytes(buffer), content_encoding)) >= threshold
                else:
                    reached = len(buffer) >= threshold
                if reached:
                    truncated = True
                    break
        finally:
            await response.aclose()
        return RawResponse(
            status=response.status_code,
            url=str(response.url),
            headers=dict(response.headers),
            fragment=bytes(buffer),
            content_encoding=content_encoding,
            truncated=truncated,
            elapsed=time.monotonic() - start,
        )

    async def aclose(self) -> None:
        if self._owns_session:
            await self._session.close()

    async def __aenter__(self) -> CurlTransport:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
