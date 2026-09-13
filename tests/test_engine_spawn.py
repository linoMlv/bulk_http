"""Tests for the spawn-based executor (real multiprocessing, small scale)."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import orjson

from bulk_http.config import EngineConfig
from bulk_http.engine import ControlMessage
from bulk_http.engine.spawn import SpawnExecutor
from bulk_http.models import Request, Task
from bulk_http.net import FakeTransport, RawResponse


def _factory(fragment: bytes) -> Callable[[], FakeTransport]:
    def factory() -> FakeTransport:
        return FakeTransport.constant(RawResponse(status=200, url="u", fragment=fragment))

    return factory


def _batch(chunk_id: int, n: int, needle: str | None = None) -> tuple[int, list[Task]]:
    kw: dict[str, Any] = {"needles": (needle,)} if needle else {}
    tasks = [Task(source_id=i, request=Request(url=f"https://a.com/{i}", **kw)) for i in range(n)]
    return chunk_id, tasks


def test_spawn_executor_writes_per_worker_ndjson(tmp_path: Path) -> None:
    executor = SpawnExecutor(
        EngineConfig(), tmp_path, transport_factory=_factory(b"the admin panel"), workers=2
    )
    messages: list[ControlMessage] = []
    batches = [_batch(0, 2, "admin"), _batch(1, 3, "admin")]
    executor.execute(iter(batches), messages.append)
    assert len(messages) == 2
    assert sum(m.count for m in messages) == 5
    # Each control message names an existing worker file with content.
    for m in messages:
        assert (tmp_path / m.worker_file).exists()


def test_spawn_worker_functions_run_in_process(tmp_path: Path) -> None:
    # Coverage cannot see spawned subprocesses; drive the worker functions here.
    import cloudpickle

    from bulk_http.engine import spawn as spawn_mod

    spawn_mod._spawn_init(
        EngineConfig(), b"", cloudpickle.dumps(_factory(b"admin panel")), str(tmp_path), "linux"
    )
    message = spawn_mod._spawn_run_batch(_batch(0, 2, "admin"))
    assert message.count == 2
    ids = [
        orjson.loads(line)["source_id"]
        for line in (tmp_path / message.worker_file).read_bytes().splitlines()
    ]
    assert ids == [0, 1]
    spawn_mod._SPAWN_STATE.clear()


def test_default_executor_is_in_process_for_single_worker(tmp_path: Path) -> None:
    from bulk_http import Engine
    from bulk_http.engine import InProcessExecutor

    engine = Engine(EngineConfig(workers=1))
    executor = engine._default_executor(tmp_path, None)
    assert isinstance(executor, InProcessExecutor)


def test_default_executor_is_spawn_for_multiple_workers(tmp_path: Path) -> None:
    from bulk_http import Engine

    engine = Engine(EngineConfig(workers=4))
    executor = engine._default_executor(tmp_path, None)
    assert isinstance(executor, SpawnExecutor)


def test_spawn_run_batch_reuses_sink_and_closes_transport(tmp_path: Path) -> None:
    from bulk_http.config import ResolvedRequest
    from bulk_http.engine import spawn as spawn_mod
    from bulk_http.net import RawResponse

    closed: list[bool] = []

    class ClosingTransport:
        async def perform(self, resolved: ResolvedRequest) -> RawResponse:
            return RawResponse(status=200, url=resolved.url, fragment=b"ok")

        async def aclose(self) -> None:
            closed.append(True)

    tmp_path.mkdir(parents=True, exist_ok=True)
    spawn_mod._SPAWN_STATE.clear()
    spawn_mod._SPAWN_STATE.update(
        config=EngineConfig(),
        predicate=None,
        factory=lambda: ClosingTransport(),
        out_dir=str(tmp_path),
        os_name="linux",
    )
    first = spawn_mod._spawn_run_batch(_batch(0, 1))
    second = spawn_mod._spawn_run_batch(_batch(1, 1))  # reuses the same sink
    assert first.worker_file == second.worker_file
    assert closed == [True, True]
    spawn_mod._SPAWN_STATE.clear()


def test_spawn_executor_backpressure_with_many_batches(tmp_path: Path) -> None:
    executor = SpawnExecutor(
        EngineConfig(),
        tmp_path,
        transport_factory=_factory(b"ok"),
        workers=2,
        in_flight_batches=2,
    )
    messages: list[ControlMessage] = []
    batches = [_batch(i, 1) for i in range(5)]
    executor.execute(iter(batches), messages.append)
    assert len(messages) == 5
