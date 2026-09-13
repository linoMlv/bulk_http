"""Tests for building the typed evaluation context."""

from bulk_http.evaluate import build_context


def test_json_content_type_deserializes_data() -> None:
    ctx = build_context(
        status=200,
        url="https://a.com",
        headers={"Content-Type": "application/json; charset=utf-8"},
        raw=b'{"admin": true}',
    )
    assert ctx.type == "json"
    assert ctx.data == {"admin": True}
    assert ctx.dom is None
    assert ctx.text is None
    assert ctx.raw == b'{"admin": true}'


def test_truncated_json_yields_type_json_with_none_data() -> None:
    ctx = build_context(
        status=200,
        url="https://a.com",
        headers={"content-type": "application/json"},
        raw=b'{"admin": tru',
    )
    assert ctx.type == "json"
    assert ctx.data is None


def test_html_content_type_builds_dom() -> None:
    ctx = build_context(
        status=200,
        url="https://a.com",
        headers={"Content-Type": "text/html"},
        raw=b"<html><head><title>Home</title></head></html>",
    )
    assert ctx.type == "html"
    assert ctx.dom is not None
    assert ctx.dom.css_first("title").text() == "Home"


def test_text_content_type_decodes_text() -> None:
    ctx = build_context(
        status=200,
        url="https://a.com",
        headers={"Content-Type": "text/plain"},
        raw="héllo".encode(),
    )
    assert ctx.type == "text"
    assert ctx.text == "héllo"
    assert ctx.dom is None
    assert ctx.data is None


def test_missing_content_type_defaults_to_text() -> None:
    ctx = build_context(status=200, url="u", headers={}, raw=b"data")
    assert ctx.type == "text"
    assert ctx.text == "data"


def test_meta_is_attached() -> None:
    ctx = build_context(status=200, url="u", headers={}, raw=b"x", meta={"row": 9})
    assert ctx.meta == {"row": 9}


def test_content_type_found_after_other_headers() -> None:
    ctx = build_context(
        status=200,
        url="u",
        headers={"Server": "nginx", "Content-Type": "application/json"},
        raw=b"{}",
    )
    assert ctx.type == "json"
    assert ctx.data == {}
