"""A spawn-based multiprocess worker pool with bounded backpressure."""

from __future__ import annotations

import multiprocessing
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from typing import Any

import cloudpickle

from bulk_http.concurrency.processor import TaskProcessor
from bulk_http.concurrency.sizing import run
from bulk_http.config import EngineConfig
from bulk_http.evaluate import Predicate
from bulk_http.models import Result, Task
from bulk_http.net.transport import Transport

TransportFactory = Callable[[], Transport]

# Per-worker state, populated once by the pool initializer (spawn re-imports the
# module in each worker, so this starts empty there).
_STATE: dict[str, Any] = {}


def _init_worker(
    config: EngineConfig,
    predicate_bytes: bytes,
    factory_bytes: bytes,
    os_name: str | None,
) -> None:
    _STATE["config"] = config
    _STATE["predicate"] = cloudpickle.loads(predicate_bytes) if predicate_bytes else None
    _STATE["factory"] = cloudpickle.loads(factory_bytes)
    _STATE["os_name"] = os_name


def _run_batch(batch: list[Task]) -> list[Result]:
    config: EngineConfig = _STATE["config"]
    predicate: Predicate | None = _STATE["predicate"]
    factory: TransportFactory = _STATE["factory"]
    os_name: str | None = _STATE["os_name"]

    async def _go() -> list[Result]:
        transport = factory()
        processor = TaskProcessor(config, transport, predicate=predicate)
        try:
            return await processor.run_batch(batch)
        finally:
            aclose = getattr(transport, "aclose", None)
            if aclose is not None:
                await aclose()

    return run(_go(), os_name=os_name)


class WorkerPool:
    """Distribute batches of tasks across spawned worker processes.

    The predicate and transport factory are serialized once with cloudpickle
    (so lambdas and closures work under ``spawn``) and rebuilt per worker. Batches
    are submitted with bounded backpressure — at most ``in_flight_batches`` are in
    flight — and each worker is recycled after ``max_tasks_per_child`` batches.
    """

    def __init__(
        self,
        config: EngineConfig,
        *,
        transport_factory: TransportFactory,
        predicate: Predicate | None = None,
        workers: int = 1,
        in_flight_batches: int = 4,
        max_tasks_per_child: int | None = None,
        os_name: str | None = None,
    ) -> None:
        self._config = config
        self._transport_factory = transport_factory
        self._predicate = predicate
        self._workers = workers
        self._in_flight = in_flight_batches
        self._max_tasks_per_child = max_tasks_per_child
        self._os_name = os_name

    def map_batches(self, batches: Iterable[list[Task]]) -> Iterator[list[Result]]:
        predicate_bytes = cloudpickle.dumps(self._predicate) if self._predicate else b""
        factory_bytes = cloudpickle.dumps(self._transport_factory)
        context = multiprocessing.get_context("spawn")
        with context.Pool(
            processes=self._workers,
            maxtasksperchild=self._max_tasks_per_child,
            initializer=_init_worker,
            initargs=(self._config, predicate_bytes, factory_bytes, self._os_name),
        ) as pool:
            pending: deque[Any] = deque()
            iterator = iter(batches)
            for _ in range(self._in_flight):
                batch = next(iterator, None)
                if batch is None:
                    break
                pending.append(pool.apply_async(_run_batch, (batch,)))
            while pending:
                yield pending.popleft().get()
                batch = next(iterator, None)
                if batch is not None:
                    pending.append(pool.apply_async(_run_batch, (batch,)))
