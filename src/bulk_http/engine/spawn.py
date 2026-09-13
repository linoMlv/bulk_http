"""A spawn-based executor: per-worker NDJSON output, one control message per batch."""

from __future__ import annotations

import multiprocessing
import os
from collections import deque
from collections.abc import Callable, Iterable
from typing import Any

import cloudpickle

from bulk_http.concurrency.processor import TaskProcessor
from bulk_http.concurrency.sizing import run
from bulk_http.engine.control import ControlMessage
from bulk_http.engine.robots_support import make_robots_gate
from bulk_http.evaluate import Predicate
from bulk_http.metrics import compute_batch_stats
from bulk_http.models import Task
from bulk_http.net.transport import Transport
from bulk_http.proxies import DomainRateLimiter, ProxyPool
from bulk_http.sinks import NdjsonWorkerSink

TransportFactory = Callable[[], Transport]
Batch = tuple[int, list[Task]]
OnControl = Callable[[ControlMessage], None]

_SPAWN_STATE: dict[str, Any] = {}


def _spawn_init(
    config: object,
    predicate_bytes: bytes,
    factory_bytes: bytes,
    out_dir: str,
    os_name: str | None,
    proxies: list[str] | None = None,
    per_domain_rate_limit: float | None = None,
) -> None:
    _SPAWN_STATE.clear()
    _SPAWN_STATE["config"] = config
    _SPAWN_STATE["predicate"] = cloudpickle.loads(predicate_bytes) if predicate_bytes else None
    _SPAWN_STATE["factory"] = cloudpickle.loads(factory_bytes)
    _SPAWN_STATE["out_dir"] = out_dir
    _SPAWN_STATE["os_name"] = os_name
    _SPAWN_STATE["proxies"] = proxies
    _SPAWN_STATE["per_domain_rate_limit"] = per_domain_rate_limit
    os.makedirs(out_dir, exist_ok=True)


def _spawn_run_batch(item: Batch) -> ControlMessage:
    chunk_id, batch = item
    state = _SPAWN_STATE
    if "sink" not in state:
        filename = f"worker-{os.getpid()}.ndjson"
        state["filename"] = filename
        state["sink"] = NdjsonWorkerSink(os.path.join(state["out_dir"], filename))

    if "proxy_pool" not in state:
        proxies = state.get("proxies")
        state["proxy_pool"] = ProxyPool(proxies) if proxies else None
        rate = state.get("per_domain_rate_limit")
        state["rate_limiter"] = DomainRateLimiter(rate) if rate is not None else None

    async def _go() -> list[Any]:
        transport = state["factory"]()
        processor = TaskProcessor(
            state["config"],
            transport,
            predicate=state["predicate"],
            proxy_pool=state["proxy_pool"],
            rate_limiter=state["rate_limiter"],
            robots=make_robots_gate(state["config"], transport),
        )
        try:
            return await processor.run_batch(batch)
        finally:
            aclose = getattr(transport, "aclose", None)
            if aclose is not None:
                await aclose()

    results = run(_go(), os_name=state["os_name"])
    sink = state["sink"]
    count = 0
    for result in results:
        if result.matched:
            sink.write(result)
            count += 1
    offset = sink.commit()
    stats = compute_batch_stats(results)
    return ControlMessage(chunk_id, state["filename"], offset, count, stats)


class SpawnExecutor:
    """Distribute batches across spawned workers, each owning one NDJSON file.

    The predicate and transport factory are cloudpickled once per worker. Each
    worker writes validated results to ``worker-<pid>.ndjson`` and returns one
    control message per batch; submission is bounded to ``in_flight_batches``.
    """

    def __init__(
        self,
        config: object,
        out_dir: str | os.PathLike[str],
        *,
        transport_factory: TransportFactory,
        predicate: Predicate | None = None,
        workers: int = 1,
        in_flight_batches: int = 4,
        max_tasks_per_child: int | None = None,
        os_name: str | None = None,
        proxies: list[str] | None = None,
        per_domain_rate_limit: float | None = None,
    ) -> None:
        self._config = config
        self._out_dir = str(out_dir)
        self._factory = transport_factory
        self._predicate = predicate
        self._workers = workers
        self._in_flight = in_flight_batches
        self._max_tasks_per_child = max_tasks_per_child
        self._os_name = os_name
        self._proxies = proxies
        self._per_domain_rate_limit = per_domain_rate_limit

    def execute(self, batches: Iterable[Batch], on_control: OnControl) -> None:
        predicate_bytes = cloudpickle.dumps(self._predicate) if self._predicate else b""
        factory_bytes = cloudpickle.dumps(self._factory)
        context = multiprocessing.get_context("spawn")
        with context.Pool(
            processes=self._workers,
            maxtasksperchild=self._max_tasks_per_child,
            initializer=_spawn_init,
            initargs=(
                self._config,
                predicate_bytes,
                factory_bytes,
                self._out_dir,
                self._os_name,
                self._proxies,
                self._per_domain_rate_limit,
            ),
        ) as pool:
            pending: deque[Any] = deque()
            iterator = iter(batches)
            for _ in range(self._in_flight):
                item = next(iterator, None)
                if item is None:
                    break
                pending.append(pool.apply_async(_spawn_run_batch, (item,)))
            while pending:
                on_control(pending.popleft().get())
                item = next(iterator, None)
                if item is not None:
                    pending.append(pool.apply_async(_spawn_run_batch, (item,)))
