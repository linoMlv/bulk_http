"""The production transport backed by curl_cffi (libcurl-impersonate)."""

from __future__ import annotations

import time
from types import TracebackType
from typing import Any

from curl_cffi import CurlError
from curl_cffi.const import CurlHttpVersion
from curl_cffi.requests import AsyncSession

from bulk_http._types import HttpVersion
from bulk_http.config import ResolvedRequest
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


class CurlTransport:
    """Perform requests with curl_cffi, keeping fingerprint impersonation.

    curl's automatic decompression is disabled (``accept_encoding=None``) so the
    fragment is the raw wire body; the advertised ``Accept-Encoding`` is set
    explicitly to stay consistent with the impersonated profile. Decompression is
    handled downstream, which is what makes Stream-Cut's wire semantics possible.
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

    async def perform(self, resolved: ResolvedRequest) -> RawResponse:
        start = time.monotonic()
        try:
            response = await self._session.request(
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
            )
        except CurlError as error:
            return RawResponse(
                status=None,
                url=resolved.url,
                error=type(error).__name__,
                elapsed=time.monotonic() - start,
            )
        return RawResponse(
            status=response.status_code,
            url=str(response.url),
            headers=dict(response.headers),
            fragment=response.content,
            content_encoding=response.headers.get("Content-Encoding"),
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
