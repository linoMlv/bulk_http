"""Tests for the method-aware retry policy."""

from bulk_http.config import EngineConfig
from bulk_http.models import Request
from bulk_http.net import FakeTransport, RawResponse
from bulk_http.net.retry import perform_with_retries


async def _noop_sleep(delay: float) -> None:
    return None


def _ok() -> RawResponse:
    return RawResponse(status=200, url="https://a.com", fragment=b"ok")


def _err() -> RawResponse:
    return RawResponse(status=None, url="https://a.com", error="connect_timeout")


def _rate_limited() -> RawResponse:
    return RawResponse(status=429, url="https://a.com")


async def test_success_performs_once() -> None:
    t = FakeTransport.constant(_ok())
    resolved = EngineConfig(retries=3).effective(Request(url="https://a.com"))
    out = await perform_with_retries(t, resolved, sleep=_noop_sleep, jitter=lambda: 0.0)
    assert out.status == 200
    assert len(t.calls) == 1


async def test_transport_error_retried_for_idempotent_until_success() -> None:
    t = FakeTransport.sequence([_err(), _err(), _ok()])
    resolved = EngineConfig(retries=3).effective(Request(url="https://a.com", method="GET"))
    out = await perform_with_retries(t, resolved, sleep=_noop_sleep, jitter=lambda: 0.0)
    assert out.status == 200
    assert len(t.calls) == 3


async def test_transport_error_not_retried_for_non_idempotent() -> None:
    t = FakeTransport.constant(_err())
    resolved = EngineConfig(retries=3).effective(Request(url="https://a.com", method="POST"))
    out = await perform_with_retries(t, resolved, sleep=_noop_sleep, jitter=lambda: 0.0)
    assert out.error == "connect_timeout"
    assert len(t.calls) == 1


async def test_non_idempotent_retried_when_opted_in() -> None:
    t = FakeTransport.sequence([_err(), _ok()])
    resolved = EngineConfig(retries=3, retry_non_idempotent=True).effective(
        Request(url="https://a.com", method="POST")
    )
    out = await perform_with_retries(t, resolved, sleep=_noop_sleep, jitter=lambda: 0.0)
    assert out.status == 200
    assert len(t.calls) == 2


async def test_retries_are_bounded() -> None:
    t = FakeTransport.constant(_err())
    resolved = EngineConfig(retries=2).effective(Request(url="https://a.com"))
    out = await perform_with_retries(t, resolved, sleep=_noop_sleep, jitter=lambda: 0.0)
    assert out.error == "connect_timeout"
    assert len(t.calls) == 3  # 1 initial + 2 retries


async def test_429_triggers_retry_then_returns_final() -> None:
    t = FakeTransport.sequence([_rate_limited(), _ok()])
    resolved = EngineConfig(retries=3).effective(Request(url="https://a.com"))
    out = await perform_with_retries(t, resolved, sleep=_noop_sleep, jitter=lambda: 0.0)
    assert out.status == 200
    assert len(t.calls) == 2


async def test_5xx_is_not_retried() -> None:
    t = FakeTransport.constant(RawResponse(status=503, url="https://a.com"))
    resolved = EngineConfig(retries=3).effective(Request(url="https://a.com"))
    out = await perform_with_retries(t, resolved, sleep=_noop_sleep, jitter=lambda: 0.0)
    assert out.status == 503
    assert len(t.calls) == 1


async def test_backoff_delays_grow_exponentially() -> None:
    delays: list[float] = []

    async def record(delay: float) -> None:
        delays.append(delay)

    t = FakeTransport.constant(_err())
    resolved = EngineConfig(retries=3).effective(Request(url="https://a.com"))
    await perform_with_retries(t, resolved, backoff_base=0.1, sleep=record, jitter=lambda: 0.0)
    assert delays == [0.1, 0.2, 0.4]


async def test_backoff_is_capped() -> None:
    delays: list[float] = []

    async def record(delay: float) -> None:
        delays.append(delay)

    t = FakeTransport.constant(_err())
    resolved = EngineConfig(retries=5).effective(Request(url="https://a.com"))
    await perform_with_retries(
        t, resolved, backoff_base=1.0, backoff_cap=3.0, sleep=record, jitter=lambda: 0.0
    )
    assert max(delays) <= 3.0
