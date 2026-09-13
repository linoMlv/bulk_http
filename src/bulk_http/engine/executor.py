"""Batch executors: run batches and persist per-worker NDJSON output."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable

from bulk_http.concurrency.processor import ProxyProvider, RateLimiter, TaskProcessor
from bulk_http.concurrency.sizing import run
from bulk_http.engine.control import ControlMessage
from bulk_http.engine.robots_support import make_robots_gate
from bulk_http.evaluate import Predicate
from bulk_http.metrics import compute_batch_stats
from bulk_http.models import Task
from bulk_http.net.transport import Transport
from bulk_http.sinks import NdjsonWorkerSink

TransportFactory = Callable[[], Transport]
Batch = tuple[int, list[Task]]
OnControl = Callable[[ControlMessage], None]


class InProcessExecutor:
    """Execute batches in the current process on one event loop and transport.

    Validated (matched) results are written to a single per-run NDJSON file;
    Each batch also reports compact statistics in its control message. After each batch the file
    is committed (flush+fsync) and a :class:`ControlMessage` is delivered.
    """

    def __init__(
        self,
        config: object,
        out_dir: str | os.PathLike[str],
        *,
        transport_factory: TransportFactory,
        predicate: Predicate | None = None,
        proxy_pool: ProxyProvider | None = None,
        rate_limiter: RateLimiter | None = None,
        os_name: str | None = None,
        filename: str = "worker-inproc.ndjson",
    ) -> None:
        self._config = config
        self._out_dir = out_dir
        self._factory = transport_factory
        self._predicate = predicate
        self._proxy_pool = proxy_pool
        self._rate_limiter = rate_limiter
        self._os_name = os_name
        self._filename = filename

    def execute(self, batches: Iterable[Batch], on_control: OnControl) -> None:
        os.makedirs(self._out_dir, exist_ok=True)
        path = os.path.join(self._out_dir, self._filename)

        async def _drive() -> None:
            transport = self._factory()
            processor = TaskProcessor(
                self._config,  # type: ignore[arg-type]
                transport,
                predicate=self._predicate,
                proxy_pool=self._proxy_pool,
                rate_limiter=self._rate_limiter,
                robots=make_robots_gate(self._config, transport),  # type: ignore[arg-type]
            )
            sink = NdjsonWorkerSink(path)
            try:
                for chunk_id, batch in batches:
                    results = await processor.run_batch(batch)
                    count = 0
                    for result in results:
                        if result.matched:
                            sink.write(result)
                            count += 1
                    offset = sink.commit()
                    stats = compute_batch_stats(results)
                    on_control(ControlMessage(chunk_id, self._filename, offset, count, stats))
            finally:
                sink.close()
                aclose = getattr(transport, "aclose", None)
                if aclose is not None:
                    await aclose()

        run(_drive(), os_name=self._os_name)
