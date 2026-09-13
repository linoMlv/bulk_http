"""Adaptive path: one attempt per pass, transient failures deferred and replayed."""

import pytest

from bulk_http.concurrency import TaskProcessor
from bulk_http.config import EngineConfig
from bulk_http.models import Request, Task
from bulk_http.net import FakeTransport, RawResponse
from bulk_http.proxies import BanSuspectedError


async def _noop_sleep(delay: float) -> None:
    return None


class RecordingLimiter:
    """Minimal adaptive-style limiter: records outcomes, optional ban after N."""

    def __init__(self, *, max_attempts: int = 5, ban_after: int | None = None) -> None:
        self.max_attempts = max_attempts
        self.records: list[tuple[str, str]] = []
        self.acquired: list[str] = []
        self._ban_after = ban_after

    async def acquire(self, domain: str) -> None:
        self.acquired.append(domain)

    def record(self, domain: str, outcome: str) -> None:
        self.records.append((domain, outcome))
        if self._ban_after is not None and len(self.records) >= self._ban_after:
            raise BanSuspectedError("stop")


def _proc(transport: FakeTransport, limiter: RecordingLimiter) -> TaskProcessor:
    return TaskProcessor(
        EngineConfig(), transport, rate_limiter=limiter, sleep=_noop_sleep, jitter=lambda: 0.0
    )


def _task(url: str = "https://a.com/x", **overrides: object) -> Task:
    return Task(source_id=0, request=Request(url=url, **overrides))  # type: ignore[arg-type]


async def test_single_attempt_records_outcome() -> None:
    limiter = RecordingLimiter()
    proc = _proc(FakeTransport.constant(RawResponse(status=200, url="u", fragment=b"ok")), limiter)
    result = await proc.process(_task())
    assert result.status == 200
    assert limiter.acquired == ["a.com"]
    assert limiter.records == [("a.com", "ok")]  # exactly one attempt in process()


async def test_deferred_transient_is_replayed_until_success() -> None:
    # 429 then 200: run_batch does a second pass and returns 200.
    limiter = RecordingLimiter(max_attempts=5)
    transport = FakeTransport.sequence(
        [RawResponse(status=429, url="u"), RawResponse(status=200, url="u", fragment=b"ok")]
    )
    proc = _proc(transport, limiter)
    results = await proc.run_batch([_task()])
    assert results[0].status == 200
    assert [o for _, o in limiter.records] == ["rate_limited", "ok"]


async def test_deferral_is_bounded_by_max_passes() -> None:
    limiter = RecordingLimiter(max_attempts=3)
    proc = _proc(FakeTransport.constant(RawResponse(status=429, url="u")), limiter)
    results = await proc.run_batch([_task()])
    assert results[0].status == 429
    assert len(limiter.records) == 3  # three passes then give up


async def test_ban_propagates_from_run_batch() -> None:
    limiter = RecordingLimiter(max_attempts=50, ban_after=3)
    proc = _proc(FakeTransport.constant(RawResponse(status=429, url="u")), limiter)
    with pytest.raises(BanSuspectedError):
        await proc.run_batch([_task()])


async def test_non_idempotent_is_not_deferred() -> None:
    limiter = RecordingLimiter(max_attempts=5)
    proc = _proc(FakeTransport.constant(RawResponse(status=429, url="u")), limiter)
    results = await proc.run_batch([_task(method="POST")])
    assert results[0].status == 429
    assert len(limiter.records) == 1  # POST attempted once, not replayed


async def test_results_keep_input_order() -> None:
    limiter = RecordingLimiter(max_attempts=3)
    proc = _proc(FakeTransport.constant(RawResponse(status=200, url="u")), limiter)
    tasks = [Task(source_id=i, request=Request(url=f"https://a.com/{i}")) for i in range(4)]
    results = await proc.run_batch(tasks)
    assert [r.source_id for r in results] == [0, 1, 2, 3]


async def test_transport_error_is_deferred_then_recovers() -> None:
    limiter = RecordingLimiter(max_attempts=5)
    transport = FakeTransport.sequence(
        [
            RawResponse(status=None, url="u", error="ConnectTimeout"),
            RawResponse(status=200, url="u", fragment=b"ok"),
        ]
    )
    proc = _proc(transport, limiter)
    results = await proc.run_batch([_task()])
    assert results[0].status == 200


async def test_plain_limiter_without_record_runs_single_pass() -> None:
    class OnlyAcquire:
        async def acquire(self, domain: str) -> None:
            return None

    proc = TaskProcessor(
        EngineConfig(),
        FakeTransport.constant(RawResponse(status=200, url="u")),
        rate_limiter=OnlyAcquire(),
        sleep=_noop_sleep,
        jitter=lambda: 0.0,
    )
    results = await proc.run_batch([_task()])
    assert results[0].status == 200
