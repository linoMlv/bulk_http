"""Tests for the Request model and shared type literals."""

from dataclasses import FrozenInstanceError

import pytest

from bulk_http.models import Request


def test_request_requires_url_and_defaults_are_none() -> None:
    req = Request(url="https://example.com")
    assert req.url == "https://example.com"
    assert req.method == "GET"
    # Network overrides default to None (meaning "inherit engine defaults").
    assert req.stream_cut is None
    assert req.proxy is None
    assert req.impersonate is None
    assert req.needles == ()
    assert req.meta == {}


def test_request_is_frozen() -> None:
    req = Request(url="https://example.com")
    with pytest.raises(FrozenInstanceError):
        req.url = "https://other.com"  # type: ignore[misc]


def test_request_rejects_empty_url() -> None:
    with pytest.raises(ValueError):
        Request(url="")


def test_request_rejects_unknown_method() -> None:
    with pytest.raises(ValueError):
        Request(url="https://example.com", method="FETCH")  # type: ignore[arg-type]


def test_request_rejects_non_positive_stream_cut() -> None:
    with pytest.raises(ValueError):
        Request(url="https://example.com", stream_cut=0)


def test_request_accepts_overrides_and_data() -> None:
    req = Request(
        url="https://example.com",
        method="POST",
        headers={"X-Api-Key": "abc"},
        body=b"payload",
        needles=("admin", "root"),
        expected_status=200,
        proxy="http://127.0.0.1:8080",
        stream_cut=15_000,
        cut_on="decoded",
        fast_status=True,
        meta={"row": 42},
    )
    assert req.method == "POST"
    assert req.headers == {"X-Api-Key": "abc"}
    assert req.needles == ("admin", "root")
    assert req.expected_status == 200
    assert req.cut_on == "decoded"
    assert req.meta["row"] == 42


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cut_on": "bogus"},
        {"http_version": "h5"},
        {"accept_encoding": "brotli"},
        {"stream_cut": 0},
        {"stream_cut": -1},
        {"max_redirects": -1},
        {"timeout": 0},
        {"total_timeout": -2.0},
        {"retries": -1},
    ],
)
def test_request_rejects_invalid_overrides(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        Request(url="https://example.com", **kwargs)  # type: ignore[arg-type]
