"""Tests for the in-process batch executor."""

from collections.abc import Callable
from pathlib import Path

import orjson

from bulk_http.config import EngineConfig
from bulk_http.engine import ControlMessage, InProcessExecutor
from bulk_http.models import Request, Task
from bulk_http.net import FakeTransport, RawResponse


def _factory(fragment: bytes) -> Callable[[], FakeTransport]:
    def factory() -> FakeTransport:
        return FakeTransport.constant(RawResponse(status=200, url="u", fragment=fragment))

    return factory


def _batch(chunk_id: int, urls: list[str], **overrides: object) -> tuple[int, list[Task]]:
    tasks = [
        Task(source_id=i, request=Request(url=u, **overrides))  # type: ignore[arg-type]
        for i, u in enumerate(urls)
    ]
    return chunk_id, tasks


def test_executor_writes_matched_results_and_reports_control(tmp_path: Path) -> None:
    executor = InProcessExecutor(
        EngineConfig(), tmp_path, transport_factory=_factory(b"the admin panel")
    )
    messages: list[ControlMessage] = []
    batches = [_batch(0, ["https://a.com", "https://b.com"], needles=("admin",))]
    executor.execute(iter(batches), messages.append)
    assert len(messages) == 1
    assert messages[0].chunk_id == 0
    assert messages[0].count == 2  # both match "admin"
    lines = (tmp_path / messages[0].worker_file).read_bytes().splitlines()
    assert len(lines) == 2
    assert orjson.loads(lines[0])["matched"] is True


def test_executor_offset_is_durable_and_grows(tmp_path: Path) -> None:
    executor = InProcessExecutor(EngineConfig(), tmp_path, transport_factory=_factory(b"ok"))
    messages: list[ControlMessage] = []
    batches = [
        _batch(0, ["https://a.com"]),
        _batch(1, ["https://b.com"]),
    ]
    executor.execute(iter(batches), messages.append)
    assert messages[0].offset < messages[1].offset


def test_executor_reports_batch_stats_for_all_results(tmp_path: Path) -> None:
    executor = InProcessExecutor(
        EngineConfig(),
        tmp_path,
        transport_factory=_factory(b"nope"),
    )
    messages: list[ControlMessage] = []
    batches = [_batch(0, ["https://a.com", "https://b.com"], needles=("admin",))]
    executor.execute(iter(batches), messages.append)
    stats = messages[0].stats
    assert stats.total == 2
    assert stats.matched == 0  # needle absent
    assert stats.by_status == {200: 2}


def test_executor_only_writes_matched(tmp_path: Path) -> None:
    executor = InProcessExecutor(EngineConfig(), tmp_path, transport_factory=_factory(b"nope"))
    messages: list[ControlMessage] = []
    executor.execute(iter([_batch(0, ["https://a.com"], needles=("admin",))]), messages.append)
    assert messages[0].count == 0
    assert (tmp_path / messages[0].worker_file).read_bytes() == b""


def test_executor_closes_transport_with_aclose(tmp_path: Path) -> None:
    from bulk_http.config import ResolvedRequest

    closed: list[bool] = []

    class ClosingTransport:
        async def perform(self, resolved: ResolvedRequest) -> RawResponse:
            return RawResponse(status=200, url=resolved.url, fragment=b"ok")

        async def aclose(self) -> None:
            closed.append(True)

    executor = InProcessExecutor(
        EngineConfig(), tmp_path, transport_factory=lambda: ClosingTransport()
    )
    executor.execute(iter([_batch(0, ["https://a.com"])]), lambda m: None)
    assert closed == [True]
