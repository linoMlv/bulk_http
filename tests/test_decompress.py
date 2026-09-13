"""Tests for tolerant, partial fragment decompression."""

import gzip
import zlib

import pytest

from bulk_http.decompress import decompress_fragment

CONTENT = ("<html><head><title>Home</title></head>" + "x" * 5000).encode()
# A larger, less-compressible payload so a truncated stream still decodes a prefix.
VARIED = b"".join(f"<li>item number {i} of the list</li>\n".encode() for i in range(3000))


def test_identity_and_empty_encoding_return_data_unchanged() -> None:
    assert decompress_fragment(CONTENT, "identity") == CONTENT
    assert decompress_fragment(CONTENT, "") == CONTENT
    assert decompress_fragment(CONTENT, None) == CONTENT


def test_unknown_encoding_raises() -> None:
    with pytest.raises(ValueError):
        decompress_fragment(CONTENT, "snappy")


def test_gzip_full_round_trip() -> None:
    assert decompress_fragment(gzip.compress(CONTENT), "gzip") == CONTENT


def test_gzip_truncated_yields_prefix_without_error() -> None:
    comp = gzip.compress(VARIED)
    out = decompress_fragment(comp[: len(comp) // 2], "gzip")
    assert len(out) > 0
    assert VARIED.startswith(out)


def test_deflate_zlib_wrapped_round_trip() -> None:
    assert decompress_fragment(zlib.compress(CONTENT), "deflate") == CONTENT


def test_deflate_raw_round_trip() -> None:
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    raw = compressor.compress(CONTENT) + compressor.flush()
    assert decompress_fragment(raw, "deflate") == CONTENT


def test_deflate_truncated_yields_prefix() -> None:
    comp = zlib.compress(VARIED)
    out = decompress_fragment(comp[: len(comp) // 2], "deflate")
    assert len(out) > 0
    assert VARIED.startswith(out)


def test_encoding_is_case_insensitive_and_trimmed() -> None:
    assert decompress_fragment(gzip.compress(CONTENT), "  GZIP  ") == CONTENT


def test_multi_encoding_with_identity_step_is_skipped() -> None:
    # "gzip, identity" means: identity applied last (no-op), then gzip undone.
    assert decompress_fragment(gzip.compress(CONTENT), "gzip, identity") == CONTENT


def test_brotli_full_round_trip() -> None:
    import brotli

    assert decompress_fragment(brotli.compress(CONTENT), "br") == CONTENT


def test_brotli_truncated_is_tolerant_and_prefix() -> None:
    import brotli

    comp = brotli.compress(VARIED)
    out = decompress_fragment(comp[: len(comp) * 3 // 4], "br")
    # May be empty for a single meta-block, but must never raise and stays a prefix.
    assert VARIED.startswith(out)


def test_brotli_corrupt_data_is_tolerated_not_raised() -> None:
    # Invalid brotli bytes must not raise: the decoder stops and returns what it has.
    out = decompress_fragment(b"\xff\xfe\xfd\xfc" * 64, "br")
    assert isinstance(out, bytes)
