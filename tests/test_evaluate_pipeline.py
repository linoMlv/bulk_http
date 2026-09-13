"""Tests for the full evaluation pipeline."""

import gzip

from bulk_http.evaluate import PatternMatcher, evaluate

EMPTY = PatternMatcher(())


def _boom(ctx: object) -> bool:
    raise AssertionError("predicate should not be called")


def test_no_conditions_matches() -> None:
    matched, ctx = evaluate(
        status=200, url="u", headers={}, fragment=b"body", content_encoding=None, matcher=EMPTY
    )
    assert matched is True
    assert ctx is None


def test_expected_status_only() -> None:
    ok, _ = evaluate(
        status=200,
        url="u",
        headers={},
        fragment=b"",
        content_encoding=None,
        matcher=EMPTY,
        expected_status=200,
    )
    bad, _ = evaluate(
        status=404,
        url="u",
        headers={},
        fragment=b"",
        content_encoding=None,
        matcher=EMPTY,
        expected_status=200,
    )
    assert ok is True
    assert bad is False


def test_needle_search_on_plain_fragment() -> None:
    m = PatternMatcher(("admin",))
    hit, _ = evaluate(
        status=200,
        url="u",
        headers={},
        fragment=b"the admin panel",
        content_encoding=None,
        matcher=m,
    )
    miss, _ = evaluate(
        status=200, url="u", headers={}, fragment=b"nothing", content_encoding=None, matcher=m
    )
    assert hit is True
    assert miss is False


def test_needle_search_on_compressed_fragment() -> None:
    m = PatternMatcher(("secret-token",))
    body = gzip.compress(b"<html>secret-token here</html>")
    hit, _ = evaluate(
        status=200, url="u", headers={}, fragment=body, content_encoding="gzip", matcher=m
    )
    assert hit is True


def test_predicate_receives_typed_context() -> None:
    seen: dict[str, object] = {}

    def predicate(ctx: object) -> bool:
        seen["type"] = ctx.type  # type: ignore[attr-defined]
        return ctx.data.get("admin") is True  # type: ignore[attr-defined]

    matched, ctx = evaluate(
        status=200,
        url="u",
        headers={"Content-Type": "application/json"},
        fragment=b'{"admin": true}',
        content_encoding=None,
        matcher=EMPTY,
        predicate=predicate,
        meta={"row": 1},
    )
    assert matched is True
    assert seen["type"] == "json"
    assert ctx is not None
    assert ctx.meta == {"row": 1}


def test_and_semantics_all_must_pass() -> None:
    m = PatternMatcher(("admin",))
    matched, _ = evaluate(
        status=200,
        url="u",
        headers={"Content-Type": "text/html"},
        fragment=b"<html>admin</html>",
        content_encoding=None,
        matcher=m,
        expected_status=200,
        predicate=lambda ctx: ctx.dom is not None and ctx.dom.css_first("html") is not None,
    )
    assert matched is True


def test_status_mismatch_short_circuits_before_predicate() -> None:
    matched, ctx = evaluate(
        status=500,
        url="u",
        headers={},
        fragment=b"x",
        content_encoding=None,
        matcher=EMPTY,
        expected_status=200,
        predicate=_boom,
    )
    assert matched is False
    assert ctx is None


def test_needle_miss_short_circuits_before_predicate() -> None:
    m = PatternMatcher(("admin",))
    matched, _ = evaluate(
        status=200,
        url="u",
        headers={},
        fragment=b"guest",
        content_encoding=None,
        matcher=m,
        predicate=_boom,
    )
    assert matched is False


def test_predicate_false_fails_match() -> None:
    matched, _ = evaluate(
        status=200,
        url="u",
        headers={"Content-Type": "text/plain"},
        fragment=b"x",
        content_encoding=None,
        matcher=EMPTY,
        predicate=lambda ctx: False,
    )
    assert matched is False
