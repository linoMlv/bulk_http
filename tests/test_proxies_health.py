"""Tests for proxy outcome classification and the per-proxy circuit breaker."""

from bulk_http.net import RawResponse
from bulk_http.proxies import ProxyHealth, classify_outcome


def _resp(status: int | None = None, error: str | None = None) -> RawResponse:
    return RawResponse(status=status, url="u", error=error)


def test_classify_transport_error() -> None:
    assert classify_outcome(_resp(error="ConnectionError")) == "transport_error"


def test_classify_proxy_auth_407_is_transport() -> None:
    assert classify_outcome(_resp(status=407)) == "transport_error"


def test_classify_rate_limited_429() -> None:
    assert classify_outcome(_resp(status=429)) == "rate_limited"


def test_classify_origin_errors() -> None:
    assert classify_outcome(_resp(status=403)) == "origin_error"
    assert classify_outcome(_resp(status=503)) == "origin_error"


def test_classify_ok() -> None:
    assert classify_outcome(_resp(status=200)) == "ok"
    assert classify_outcome(_resp(status=301)) == "ok"


def test_health_available_initially() -> None:
    health = ProxyHealth()
    assert health.is_available(now=0.0) is True


def test_health_quarantines_after_transport_failure_rate() -> None:
    health = ProxyHealth(window=10, failure_threshold=0.5, min_samples=4, cooldown=60.0)
    for _ in range(4):
        health.record("transport_error", now=1.0)
    assert health.is_available(now=1.0) is False
    # After cooldown it recovers.
    assert health.is_available(now=1.0 + 61.0) is True


def test_health_not_quarantined_below_min_samples() -> None:
    health = ProxyHealth(min_samples=5)
    health.record("transport_error", now=1.0)
    assert health.is_available(now=1.0) is True


def test_origin_errors_do_not_quarantine_proxy() -> None:
    health = ProxyHealth(min_samples=1, failure_threshold=0.1)
    for _ in range(10):
        health.record("origin_error", now=1.0)
    assert health.is_available(now=1.0) is True


def test_success_keeps_proxy_available() -> None:
    health = ProxyHealth(window=10, failure_threshold=0.5, min_samples=4)
    health.record("transport_error", now=1.0)
    for _ in range(9):
        health.record("ok", now=1.0)
    assert health.is_available(now=1.0) is True


def test_rate_limited_triggers_backoff_not_quarantine() -> None:
    health = ProxyHealth(rate_limit_backoff=30.0)
    health.record("rate_limited", now=10.0)
    assert health.is_available(now=10.0) is False
    assert health.is_available(now=41.0) is True
