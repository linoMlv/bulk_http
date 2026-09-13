"""Unit tests for the shared build_request helper."""

import pytest

from bulk_http.sources._build import build_request


def test_build_request_basic_url() -> None:
    req = build_request({"url": "https://a.com"})
    assert req.url == "https://a.com"


def test_build_request_method_uppercased() -> None:
    assert build_request({"url": "u", "method": "post"}).method == "POST"


def test_build_request_str_and_dict_fields() -> None:
    req = build_request(
        {
            "url": "u",
            "impersonate": "safari",
            "cut_on": "decoded",
            "http_version": "h2",
            "accept_encoding": "identity",
            "proxy": "http://p:1",
            "headers": {"A": "b"},
            "cookies": {"s": "1"},
        }
    )
    assert req.impersonate == "safari"
    assert req.cut_on == "decoded"
    assert req.http_version == "h2"
    assert req.accept_encoding == "identity"
    assert req.proxy == "http://p:1"
    assert req.headers == {"A": "b"}
    assert req.cookies == {"s": "1"}


def test_build_request_numeric_and_bool_coercion() -> None:
    req = build_request(
        {
            "url": "u",
            "stream_cut": "1500",
            "max_redirects": "3",
            "retries": "4",
            "timeout": "2.5",
            "total_timeout": "10",
            "fast_status": "true",
            "verify_ssl": "0",
            "follow_redirects": "yes",
            "retry_non_idempotent": "no",
        }
    )
    assert req.stream_cut == 1500
    assert req.max_redirects == 3
    assert req.retries == 4
    assert req.timeout == 2.5
    assert req.total_timeout == 10.0
    assert req.fast_status is True
    assert req.verify_ssl is False
    assert req.follow_redirects is True
    assert req.retry_non_idempotent is False


def test_build_request_body_from_str_and_bytes() -> None:
    assert build_request({"url": "u", "body": "hi"}).body == b"hi"
    assert build_request({"url": "u", "body": b"raw"}).body == b"raw"


def test_build_request_needle_and_needles() -> None:
    assert build_request({"url": "u", "needle": "admin"}).needles == ("admin",)
    assert build_request({"url": "u", "needles": ["a", "b"]}).needles == ("a", "b")
    assert build_request({"url": "u", "needles": "solo"}).needles == ("solo",)
    assert build_request({"url": "u", "needles": 42}).needles == ("42",)


def test_build_request_expected_status_scalar_and_collection() -> None:
    assert build_request({"url": "u", "expected_status": "200"}).expected_status == 200
    assert build_request({"url": "u", "expected_status": [200, 301]}).expected_status == frozenset(
        {200, 301}
    )


def test_build_request_meta_explicit_and_unknown_keys() -> None:
    req = build_request({"url": "u", "meta": {"a": 1}, "campaign": "x"})
    assert req.meta == {"a": 1, "campaign": "x"}


def test_build_request_extra_meta_argument_merges() -> None:
    req = build_request({"url": "u", "extra": "y"}, {"kept": "z"})
    assert req.meta == {"kept": "z", "extra": "y"}


def test_build_request_bool_bool_passthrough() -> None:
    assert build_request({"url": "u", "fast_status": True}).fast_status is True


def test_build_request_invalid_bool_raises() -> None:
    with pytest.raises(ValueError):
        build_request({"url": "u", "fast_status": "maybe"})
