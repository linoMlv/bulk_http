"""Tolerant, partial decompression of network fragments.

Stream-Cut and Fast-Status truncate transfers mid-stream, so a received fragment
is almost always an incomplete compressed stream. These decoders return whatever
can be decoded from the prefix and deliberately ignore end-of-stream errors
(CRC/length checks are not required for pattern search).
"""

from __future__ import annotations

import zlib
from collections.abc import Callable

import brotli
import zstandard

_CHUNK = 8192


def _inflate(data: bytes, wbits: int) -> bytes:
    decompressor = zlib.decompressobj(wbits)
    out = bytearray()
    try:
        out += decompressor.decompress(data)
        out += decompressor.flush()
    except zlib.error:
        pass
    return bytes(out)


def _gzip(data: bytes) -> bytes:
    return _inflate(data, 16 + zlib.MAX_WBITS)


def _deflate(data: bytes) -> bytes:
    # HTTP "deflate" is ambiguous: prefer zlib-wrapped, fall back to raw deflate.
    zlib_wrapped = _inflate(data, zlib.MAX_WBITS)
    if zlib_wrapped:
        return zlib_wrapped
    return _inflate(data, -zlib.MAX_WBITS)


def _brotli(data: bytes) -> bytes:
    decompressor = brotli.Decompressor()
    out = bytearray()
    for start in range(0, len(data), _CHUNK):
        try:
            out += decompressor.process(data[start : start + _CHUNK])
        except brotli.error:
            break
    return bytes(out)


def _zstd(data: bytes) -> bytes:
    decompressor = zstandard.ZstdDecompressor().decompressobj()
    out = bytearray()
    for start in range(0, len(data), _CHUNK):
        try:
            out += decompressor.decompress(data[start : start + _CHUNK])
        except zstandard.ZstdError:
            break
    return bytes(out)


_DECODERS: dict[str, Callable[[bytes], bytes]] = {
    "gzip": _gzip,
    "x-gzip": _gzip,
    "deflate": _deflate,
    "br": _brotli,
    "zstd": _zstd,
}


def decompress_fragment(data: bytes, encoding: str | None) -> bytes:
    """Decompress a possibly-truncated ``data`` fragment for ``encoding``.

    ``encoding`` follows the ``Content-Encoding`` header: an empty value or
    ``identity`` returns the data unchanged; multiple comma-separated codings are
    undone in reverse order. Unknown codings raise :class:`ValueError`.
    """
    normalized = (encoding or "").strip().lower()
    if normalized in ("", "identity"):
        return data
    codings = [part.strip() for part in normalized.split(",") if part.strip()]
    out = data
    for coding in reversed(codings):
        if coding in ("", "identity"):
            continue
        try:
            decoder = _DECODERS[coding]
        except KeyError:
            raise ValueError(f"unsupported content encoding: {coding!r}") from None
        out = decoder(out)
    return out
