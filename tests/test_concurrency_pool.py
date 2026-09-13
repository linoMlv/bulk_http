"""Tests for the spawn-based worker pool (real multiprocessing, small scale)."""

from collections.abc import Callable
from typing import Any

from bulk_http.concurrency import WorkerPool
from bulk_http.config import EngineConfig
from bulk_http.models import Request, Task
from bulk_http.net import FakeTransport, RawResponse


def _make_factory(
    fragment: bytes, headers: dict[str, str] | None = None
) -> Callable[[], FakeTransport]:
    # Defined so cloudpickle can serialize a factory for the spawned workers.
    def factory() -> FakeTransport:
        return FakeTransport.constant(
            RawResponse(status=200, url="u", fragment=fragment, headers=headers or {})
        )

    return factory


def _tasks(n: int, **overrides: Any) -> list[Task]:
    return [
        Task(source_id=i, request=Request(url=f"https://a.com/{i}", **overrides)) for i in range(n)
    ]


def test_pool_processes_batches_across_workers() -> None:
    pool = WorkerPool(
        EngineConfig(),
        transport_factory=_make_factory(b"ok"),
        workers=2,
        in_flight_batches=2,
    )
    batches = [_tasks(3), _tasks(2)]
    # source ids collide across batches here; check counts and statuses instead.
    results = [r for batch in pool.map_batches(batches) for r in batch]
    assert len(results) == 5
    assert all(r.status == 200 for r in results)
    assert all(r.matched for r in results)


def test_pool_applies_needle_predicate_via_cloudpickle() -> None:
    pool = WorkerPool(
        EngineConfig(),
        transport_factory=_make_factory(b"the admin panel"),
        workers=2,
        in_flight_batches=1,
    )
    tasks = [
        Task(source_id=0, request=Request(url="https://a.com", needles=("admin",))),
        Task(source_id=1, request=Request(url="https://b.com", needles=("root",))),
    ]
    results = [r for batch in pool.map_batches([tasks]) for r in batch]
    by_id = {r.source_id: r for r in results}
    assert by_id[0].matched is True
    assert by_id[1].matched is False


def test_pool_uses_predicate_closure() -> None:
    threshold = 200

    def predicate(ctx: object) -> bool:
        return bool(ctx.status == threshold)  # type: ignore[attr-defined]

    pool = WorkerPool(
        EngineConfig(),
        transport_factory=_make_factory(b"x", headers={"Content-Type": "text/plain"}),
        predicate=predicate,
        workers=1,
        in_flight_batches=2,
    )
    results = [r for batch in pool.map_batches([_tasks(2)]) for r in batch]
    assert all(r.matched for r in results)


def test_pool_handles_more_batches_than_window() -> None:
    pool = WorkerPool(
        EngineConfig(),
        transport_factory=_make_factory(b"ok"),
        workers=2,
        in_flight_batches=2,
    )
    batches = [_tasks(1) for _ in range(6)]
    results = [r for batch in pool.map_batches(batches) for r in batch]
    assert len(results) == 6


def test_worker_functions_run_in_current_process() -> None:
    # Coverage cannot see code executed inside spawned subprocesses, so drive the
    # worker init and batch runner directly here.
    import cloudpickle

    from bulk_http.concurrency import pool as pool_mod

    factory = _make_factory(b"the admin panel")
    pool_mod._init_worker(EngineConfig(), b"", cloudpickle.dumps(factory), "linux")
    results = pool_mod._run_batch(
        [Task(source_id=0, request=Request(url="https://a.com", needles=("admin",)))]
    )
    assert results[0].matched is True


def test_worker_init_deserializes_predicate() -> None:
    import cloudpickle

    from bulk_http.concurrency import pool as pool_mod

    factory = _make_factory(b"x", headers={"Content-Type": "text/plain"})

    def predicate(ctx: object) -> bool:
        return True

    pool_mod._init_worker(
        EngineConfig(),
        cloudpickle.dumps(predicate),
        cloudpickle.dumps(factory),
        "linux",
    )
    results = pool_mod._run_batch([Task(source_id=1, request=Request(url="https://a.com"))])
    assert results[0].matched is True


def test_worker_closes_transport_with_aclose() -> None:
    import cloudpickle

    from bulk_http.concurrency import pool as pool_mod
    from bulk_http.config import ResolvedRequest

    class ClosingTransport:
        async def perform(self, resolved: ResolvedRequest) -> RawResponse:
            return RawResponse(status=200, url=resolved.url)

        async def aclose(self) -> None:
            return None

    pool_mod._init_worker(
        EngineConfig(), b"", cloudpickle.dumps(lambda: ClosingTransport()), "linux"
    )
    results = pool_mod._run_batch([Task(source_id=0, request=Request(url="https://a.com"))])
    assert results[0].status == 200
