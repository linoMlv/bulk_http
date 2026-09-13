"""Tests for the task processor and concurrent batch execution."""

from typing import Any

from bulk_http.concurrency import TaskProcessor
from bulk_http.config import EngineConfig, ResolvedRequest
from bulk_http.models import Request, Task
from bulk_http.net import FakeTransport, RawResponse


async def _noop_sleep(delay: float) -> None:
    return None


def _task(url: str, sid: int = 0, **overrides: object) -> Task:
    return Task(source_id=sid, request=Request(url=url, **overrides))  # type: ignore[arg-type]


def _ok(fragment: bytes = b"body", headers: dict[str, str] | None = None) -> RawResponse:
    return RawResponse(status=200, url="u", fragment=fragment, headers=headers or {})


def _processor(transport: FakeTransport, **kw: Any) -> TaskProcessor:
    return TaskProcessor(EngineConfig(), transport, sleep=_noop_sleep, jitter=lambda: 0.0, **kw)


async def test_process_success_no_conditions_matches() -> None:
    proc = _processor(FakeTransport.constant(_ok()))
    result = await proc.process(_task("https://a.com", 3))
    assert result.source_id == 3
    assert result.status == 200
    assert result.matched is True
    assert result.error is None


async def test_process_expected_status() -> None:
    proc = _processor(FakeTransport.constant(_ok()))
    match = await proc.process(_task("https://a.com", expected_status=200))
    miss = await proc.process(_task("https://a.com", expected_status=404))
    assert match.matched is True
    assert miss.matched is False


async def test_process_needle_search() -> None:
    proc = _processor(FakeTransport.constant(_ok(fragment=b"the admin panel")))
    hit = await proc.process(_task("https://a.com", needles=("admin",)))
    miss = await proc.process(_task("https://a.com", needles=("root",)))
    assert hit.matched is True
    assert miss.matched is False


async def test_process_predicate() -> None:
    resp = _ok(fragment=b'{"admin": true}', headers={"Content-Type": "application/json"})
    proc = TaskProcessor(
        EngineConfig(),
        FakeTransport.constant(resp),
        predicate=lambda ctx: bool(ctx.data and ctx.data.get("admin")),
        sleep=_noop_sleep,
        jitter=lambda: 0.0,
    )
    result = await proc.process(_task("https://a.com"))
    assert result.matched is True


async def test_process_transport_error() -> None:
    err = RawResponse(status=None, url="u", error="ConnectionError")
    proc = _processor(FakeTransport.constant(err))
    result = await proc.process(_task("https://a.com"))
    assert result.status is None
    assert result.error == "ConnectionError"
    assert result.matched is False


async def test_process_preserves_meta() -> None:
    proc = _processor(FakeTransport.constant(_ok()))
    result = await proc.process(_task("https://a.com", meta={"row": 7}))
    assert result.meta == {"row": 7}


class SpyPool:
    def __init__(self, proxy: str) -> None:
        self.proxy = proxy
        self.reports: list[tuple[str, str]] = []

    def select(self, *, now: float) -> str:
        return self.proxy

    def report(self, proxy: str, outcome: str, *, now: float) -> None:
        self.reports.append((proxy, outcome))


async def test_process_uses_pool_proxy_and_reports_outcome() -> None:
    transport = FakeTransport.constant(_ok())
    pool = SpyPool("http://p:1")
    proc = _processor(transport, proxy_pool=pool)
    await proc.process(_task("https://a.com"))
    assert transport.calls[-1].proxy == "http://p:1"
    assert pool.reports == [("http://p:1", "ok")]


async def test_process_respects_explicit_proxy_over_pool() -> None:
    transport = FakeTransport.constant(_ok())
    pool = SpyPool("http://pool:1")
    proc = _processor(transport, proxy_pool=pool)
    await proc.process(_task("https://a.com", proxy="http://explicit:2"))
    assert transport.calls[-1].proxy == "http://explicit:2"


class SpyLimiter:
    def __init__(self) -> None:
        self.domains: list[str] = []

    async def acquire(self, domain: str) -> None:
        self.domains.append(domain)


async def test_process_applies_rate_limiter_per_domain() -> None:
    limiter = SpyLimiter()
    proc = _processor(FakeTransport.constant(_ok()), rate_limiter=limiter)
    await proc.process(_task("https://example.com/path"))
    assert limiter.domains == ["example.com"]


async def test_run_batch_processes_all_in_order() -> None:
    proc = _processor(FakeTransport.constant(_ok()))
    tasks = [_task(f"https://a.com/{i}", i) for i in range(5)]
    results = await proc.run_batch(tasks)
    assert [r.source_id for r in results] == [0, 1, 2, 3, 4]
    assert all(r.matched for r in results)


async def test_resolved_request_type_is_used() -> None:
    # sanity: effective() produces a ResolvedRequest the processor consumes
    resolved = EngineConfig().effective(Request(url="https://a.com"))
    assert isinstance(resolved, ResolvedRequest)


class EmptyPool:
    def __init__(self) -> None:
        self.reports: list[tuple[str, str]] = []

    def select(self, *, now: float) -> str | None:
        return None

    def report(self, proxy: str, outcome: str, *, now: float) -> None:
        self.reports.append((proxy, outcome))


async def test_process_with_exhausted_pool_uses_no_proxy() -> None:
    transport = FakeTransport.constant(_ok())
    pool = EmptyPool()
    proc = _processor(transport, proxy_pool=pool)
    result = await proc.process(_task("https://a.com"))
    assert transport.calls[-1].proxy is None
    assert pool.reports == []
    assert result.status == 200
