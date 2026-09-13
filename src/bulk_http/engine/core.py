"""The Engine: orchestrate ingestion, distribution, evaluation and persistence."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, replace
from typing import Any, Protocol

from bulk_http.checkpoint import CheckpointStore, plan_resume, truncate_worker_files
from bulk_http.compliance import ComplianceFilter
from bulk_http.concurrency.chunking import chunk_batches
from bulk_http.config import EngineConfig
from bulk_http.engine.control import ControlMessage
from bulk_http.evaluate import Predicate
from bulk_http.metrics import MetricsCollector, MetricsSnapshot
from bulk_http.models import Task

Batch = tuple[int, list[Task]]
OnControl = Callable[[ControlMessage], None]


class Executor(Protocol):
    def execute(self, batches: Iterable[Batch], on_control: OnControl) -> None: ...


@dataclass(frozen=True, slots=True)
class RunSummary:
    """The outcome of a campaign run."""

    chunks: int
    matched: int
    skipped: int
    out_dir: str
    checkpoint: str | None
    metrics: MetricsSnapshot | None = None


class Engine:
    """Coordinate a campaign end to end.

    Ingestion is filtered through the compliance guardrails (allow/deny, identity
    header, authorization note) and an optional global needle, chunked into
    batches, and handed to an executor. Each committed batch advances the
    checkpoint. Re-running with the same checkpoint resumes where it stopped.
    """

    def __init__(self, config: EngineConfig | None = None, **kwargs: Any) -> None:
        self._config = config if config is not None else EngineConfig(**kwargs)

    @property
    def config(self) -> EngineConfig:
        return self._config

    def _compliance(self) -> ComplianceFilter:
        return ComplianceFilter(
            allowlist=self._config.allowlist,
            denylist=self._config.denylist,
            identity_header=self._config.identity_header,
            authorization=self._config.authorization,
        )

    def _prepare(
        self,
        source: Iterable[Task],
        compliance: ComplianceFilter,
        needle: str | None,
        counter: dict[str, int],
    ) -> Iterator[Task]:
        for task in source:
            request = task.request
            if not compliance.is_allowed(request.url):
                counter["skipped"] += 1
                continue
            changes: dict[str, Any] = {}
            if needle:
                changes["needles"] = (*request.needles, needle)
            new_headers = compliance.apply_headers(request.headers)
            if new_headers != (request.headers or {}):
                changes["headers"] = new_headers
            new_meta = compliance.annotate_meta(request.meta)
            if new_meta is not request.meta:
                changes["meta"] = new_meta
            yield Task(
                source_id=task.source_id,
                request=replace(request, **changes) if changes else request,
            )

    def _default_executor(
        self,
        out_dir: str | os.PathLike[str],
        predicate: Predicate | None,
        proxies: list[str] | None = None,
    ) -> Executor:
        import platform
        import sys

        from bulk_http.concurrency.sizing import resolve_workers
        from bulk_http.engine.executor import InProcessExecutor
        from bulk_http.engine.ratelimit_support import build_rate_limiter
        from bulk_http.engine.spawn import SpawnExecutor
        from bulk_http.net.curl import CurlTransport
        from bulk_http.proxies import ProxyPool

        os_name = "windows" if sys.platform.startswith("win") else platform.system().lower()
        workers = resolve_workers(self._config.workers, os_name=os_name, cpu_count=os.cpu_count())

        def factory() -> CurlTransport:
            return CurlTransport()

        if workers <= 1:
            pool = ProxyPool(proxies) if proxies else None
            return InProcessExecutor(
                self._config,
                out_dir,
                transport_factory=factory,
                predicate=predicate,
                proxy_pool=pool,
                rate_limiter=build_rate_limiter(self._config),
            )
        return SpawnExecutor(
            self._config,
            out_dir,
            transport_factory=factory,
            predicate=predicate,
            workers=workers,
            in_flight_batches=self._config.in_flight_batches,
            max_tasks_per_child=self._config.max_tasks_per_child,
            proxies=proxies,
        )

    def run(
        self,
        source: Iterable[Task],
        *,
        predicate: Predicate | None = None,
        out_dir: str | os.PathLike[str] = "out",
        needle: str | None = None,
        proxies: list[str] | None = None,
        executor: Executor | None = None,
        metrics_callback: Callable[[MetricsSnapshot], None] | None = None,
    ) -> RunSummary:
        compliance = self._compliance()
        counter = {"skipped": 0, "matched": 0, "chunks": 0}
        metrics = MetricsCollector()
        store = CheckpointStore(self._config.checkpoint) if self._config.checkpoint else None
        committed: set[int] = set()
        if store is not None:
            committed = self._resume(store, out_dir)

        def distributed() -> Iterator[Batch]:
            batches = enumerate(
                chunk_batches(
                    self._prepare(source, compliance, needle, counter), self._config.chunk_size
                )
            )
            for chunk_id, batch in batches:
                if chunk_id in committed:
                    continue
                if store is not None:
                    store.record_distributed(chunk_id)
                yield chunk_id, batch

        def on_control(message: ControlMessage) -> None:
            counter["matched"] += message.count
            counter["chunks"] += 1
            metrics.merge(message.stats)
            if store is not None:
                store.commit_chunk(
                    message.chunk_id, message.worker_file, message.offset, message.count
                )

        active_executor = executor or self._default_executor(out_dir, predicate, proxies)
        try:
            active_executor.execute(distributed(), on_control)
        finally:
            if store is not None:
                store.close()
        snapshot = metrics.snapshot()
        if metrics_callback is not None:
            metrics_callback(snapshot)
        return RunSummary(
            chunks=counter["chunks"],
            matched=counter["matched"],
            skipped=counter["skipped"],
            out_dir=str(out_dir),
            checkpoint=self._config.checkpoint,
            metrics=snapshot,
        )

    def _resume(self, store: CheckpointStore, out_dir: str | os.PathLike[str]) -> set[int]:
        state = store.load()
        if not state.committed:
            return set()
        plan = plan_resume(sorted(state.committed), state)
        paths = (
            [
                os.path.join(out_dir, name)
                for name in os.listdir(out_dir)
                if os.path.isfile(os.path.join(out_dir, name))
            ]
            if os.path.isdir(out_dir)
            else []
        )
        truncate_worker_files(paths, plan)
        return set(state.committed)
