"""End-to-end engine tests against the echo server, and memory invariance."""

import gc
import tracemalloc
from collections.abc import Iterator
from pathlib import Path

import orjson

from bulk_http import Engine, sources
from bulk_http.config import EngineConfig, ResolvedRequest
from bulk_http.engine import InProcessExecutor
from bulk_http.models import Request, Task
from bulk_http.net import RawResponse
from tests.support.echo_server import EchoServer


def test_end_to_end_needle_filter_against_echo(tmp_path: Path) -> None:
    with EchoServer() as server:
        engine = Engine(EngineConfig(workers=1, chunk_size=2))
        urls = [
            server.url + "/html?title=Login",
            server.url + "/html?title=Home",
            server.url + "/status/404",
        ]
        # No executor injected: exercises the default in-process + curl executor.
        summary = engine.run(sources.memory(urls), needle="Login", out_dir=tmp_path)
        assert summary.matched == 1
        line = (tmp_path / "worker-inproc.ndjson").read_bytes().splitlines()[0]
        record = orjson.loads(line)
        assert record["status"] == 200
        assert record["matched"] is True


def test_end_to_end_predicate_against_echo(tmp_path: Path) -> None:
    with EchoServer() as server:
        engine = Engine(EngineConfig(workers=1, chunk_size=5))
        urls = [server.url + "/json", server.url + "/html?title=X"]
        summary = engine.run(
            sources.memory(urls),
            predicate=lambda ctx: ctx.type == "json",
            out_dir=tmp_path,
        )
        assert summary.matched == 1  # only the JSON endpoint


class _NullTransport:
    async def perform(self, resolved: ResolvedRequest) -> RawResponse:
        return RawResponse(status=200, url=resolved.url, fragment=b"x")


def test_memory_stays_bounded_regardless_of_input_size(tmp_path: Path) -> None:
    config = EngineConfig(chunk_size=1000)

    def measure(n: int, out: Path) -> int:
        def source() -> Iterator[Task]:
            for i in range(n):
                yield Task(source_id=i, request=Request(url=f"https://a.com/{i}"))

        gc.collect()
        tracemalloc.start()
        Engine(config).run(
            source(),
            out_dir=out,
            executor=InProcessExecutor(config, out, transport_factory=_NullTransport),
        )
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return peak

    small = measure(10_000, tmp_path / "a")
    large = measure(100_000, tmp_path / "b")
    # 10x the input must not translate into anywhere near 10x the peak memory:
    # streaming keeps it bounded by the batch size, not the input size.
    assert large < small * 3
