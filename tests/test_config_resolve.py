"""Tests for resolving per-request overrides against engine defaults."""

from bulk_http.config import EngineConfig, ResolvedRequest
from bulk_http.models import Request


def test_effective_inherits_engine_defaults() -> None:
    cfg = EngineConfig(stream_cut=15_000, fast_status=True, impersonate="firefox")
    resolved = cfg.effective(Request(url="https://example.com"))
    assert isinstance(resolved, ResolvedRequest)
    assert resolved.url == "https://example.com"
    assert resolved.method == "GET"
    assert resolved.stream_cut == 15_000
    assert resolved.fast_status is True
    assert resolved.impersonate == "firefox"
    assert resolved.cut_on == "wire"
    assert resolved.verify_ssl is True
    assert resolved.proxy is None


def test_effective_request_overrides_win() -> None:
    cfg = EngineConfig(stream_cut=15_000, fast_status=False, impersonate="chrome")
    req = Request(
        url="https://example.com",
        method="POST",
        stream_cut=1_000,
        fast_status=True,
        cut_on="decoded",
        impersonate="safari",
        proxy="http://127.0.0.1:9",
        verify_ssl=False,
        retries=5,
    )
    resolved = cfg.effective(req)
    assert resolved.method == "POST"
    assert resolved.stream_cut == 1_000
    assert resolved.fast_status is True
    assert resolved.cut_on == "decoded"
    assert resolved.impersonate == "safari"
    assert resolved.proxy == "http://127.0.0.1:9"
    assert resolved.verify_ssl is False
    assert resolved.retries == 5


def test_effective_preserves_request_data() -> None:
    cfg = EngineConfig()
    req = Request(
        url="https://example.com",
        headers={"X-K": "v"},
        cookies={"s": "1"},
        body=b"data",
        needles=("admin", "root"),
        expected_status=frozenset({200, 301}),
        meta={"row": 7},
    )
    resolved = cfg.effective(req)
    assert resolved.headers == {"X-K": "v"}
    assert resolved.cookies == {"s": "1"}
    assert resolved.body == b"data"
    assert resolved.needles == ("admin", "root")
    assert resolved.expected_status == frozenset({200, 301})
    assert resolved.meta == {"row": 7}


def test_effective_stream_cut_none_means_unlimited() -> None:
    cfg = EngineConfig(stream_cut=None)
    resolved = cfg.effective(Request(url="https://example.com"))
    assert resolved.stream_cut is None


def test_resolved_request_is_idempotent_regarding_is_idempotent() -> None:
    cfg = EngineConfig()
    assert cfg.effective(Request(url="u", method="GET")).is_idempotent is True
    assert cfg.effective(Request(url="u", method="POST")).is_idempotent is False
