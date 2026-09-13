"""Tests for the per-URL total timeout across retries."""

from bulk_http.config import EngineConfig, ResolvedRequest
from bulk_http.models import Request
from bulk_http.net import FakeTransport, RawResponse
from bulk_http.net.retry import perform_with_retries


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def time(self) -> float:
        return self.t

    async def sleep(self, delay: float) -> None:
        self.t += delay


def _err() -> RawResponse:
    return RawResponse(status=None, url="https://a.com", error="timeout")


def _resolved(total_timeout: float | None, retries: int = 10) -> ResolvedRequest:
    return EngineConfig(retries=retries, total_timeout=total_timeout).effective(
        Request(url="https://a.com")
    )


async def test_no_total_timeout_uses_retry_budget() -> None:
    clock = FakeClock()
    transport = FakeTransport.constant(_err())
    out = await perform_with_retries(
        transport,
        _resolved(None, retries=3),
        backoff_base=0.1,
        sleep=clock.sleep,
        jitter=lambda: 0.0,
        clock=clock.time,
    )
    assert out.error == "timeout"
    assert len(transport.calls) == 4  # 1 + 3 retries


async def test_total_timeout_stops_early() -> None:
    clock = FakeClock()
    transport = FakeTransport.constant(_err())
    # backoff 0.1,0.2,0.4,... ; total budget 0.35s should cut well before 10 retries.
    out = await perform_with_retries(
        transport,
        _resolved(0.35, retries=10),
        backoff_base=0.1,
        sleep=clock.sleep,
        jitter=lambda: 0.0,
        clock=clock.time,
    )
    assert out.error == "timeout"
    assert len(transport.calls) < 11  # stopped by the deadline, not the retry count


async def test_total_timeout_returns_last_response() -> None:
    clock = FakeClock()
    transport = FakeTransport.constant(_err())
    out = await perform_with_retries(
        transport,
        _resolved(0.05, retries=10),
        backoff_base=1.0,
        sleep=clock.sleep,
        jitter=lambda: 0.0,
        clock=clock.time,
    )
    # First attempt runs, backoff (1.0s) exceeds the 0.05 budget -> stop after 1.
    assert out.error == "timeout"
    assert len(transport.calls) == 1


async def test_total_timeout_success_within_budget() -> None:
    clock = FakeClock()
    transport = FakeTransport.sequence([_err(), RawResponse(status=200, url="https://a.com")])
    out = await perform_with_retries(
        transport,
        _resolved(10.0, retries=5),
        backoff_base=0.1,
        sleep=clock.sleep,
        jitter=lambda: 0.0,
        clock=clock.time,
    )
    assert out.status == 200
