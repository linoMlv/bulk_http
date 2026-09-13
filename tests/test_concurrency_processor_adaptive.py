"""The processor feeds outcomes back to a rate limiter that supports record()."""

from bulk_http.concurrency import TaskProcessor
from bulk_http.concurrency.processor import RateLimiter
from bulk_http.config import EngineConfig
from bulk_http.models import Request, Task
from bulk_http.net import FakeTransport, RawResponse
from bulk_http.proxies import BanSuspectedError


async def _noop_sleep(delay: float) -> None:
    return None


class RecordingLimiter:
    def __init__(self, *, raise_ban: bool = False) -> None:
        self.records: list[tuple[str, str]] = []
        self.acquired: list[str] = []
        self._raise_ban = raise_ban

    async def acquire(self, domain: str) -> None:
        self.acquired.append(domain)

    def record(self, domain: str, outcome: str) -> None:
        self.records.append((domain, outcome))
        if self._raise_ban:
            raise BanSuspectedError("stop")


def _proc(transport: FakeTransport, limiter: RateLimiter) -> TaskProcessor:
    return TaskProcessor(
        EngineConfig(), transport, rate_limiter=limiter, sleep=_noop_sleep, jitter=lambda: 0.0
    )


async def test_processor_records_outcome_for_adaptive_limiter() -> None:
    limiter = RecordingLimiter()
    proc = _proc(FakeTransport.constant(RawResponse(status=200, url="u", fragment=b"ok")), limiter)
    await proc.process(Task(source_id=0, request=Request(url="https://a.com/x")))
    assert limiter.acquired == ["a.com"]
    assert limiter.records == [("a.com", "ok")]


async def test_processor_records_rate_limited_outcome() -> None:
    limiter = RecordingLimiter()
    proc = _proc(FakeTransport.constant(RawResponse(status=429, url="u")), limiter)
    await proc.process(Task(source_id=0, request=Request(url="https://a.com/x")))
    assert limiter.records == [("a.com", "rate_limited")]


async def test_ban_suspected_propagates_from_processor() -> None:
    import pytest

    limiter = RecordingLimiter(raise_ban=True)
    proc = _proc(FakeTransport.constant(RawResponse(status=429, url="u")), limiter)
    with pytest.raises(BanSuspectedError):
        await proc.process(Task(source_id=0, request=Request(url="https://a.com/x")))


async def test_plain_rate_limiter_without_record_is_fine() -> None:
    # A limiter without record() (the fixed-rate DomainRateLimiter) must still work.
    class OnlyAcquire:
        async def acquire(self, domain: str) -> None:
            return None

    proc = _proc(FakeTransport.constant(RawResponse(status=200, url="u")), OnlyAcquire())
    result = await proc.process(Task(source_id=0, request=Request(url="https://a.com/x")))
    assert result.status == 200
