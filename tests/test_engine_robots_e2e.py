"""End-to-end: respect_robots skips disallowed paths against the echo server."""

from pathlib import Path

import orjson

from bulk_http import Engine, sources
from bulk_http.config import EngineConfig
from tests.support.echo_server import EchoServer


def test_respect_robots_skips_disallowed_paths(tmp_path: Path) -> None:
    with EchoServer() as server:
        engine = Engine(EngineConfig(workers=1, chunk_size=5, respect_robots=True))
        urls = [server.url + "/public", server.url + "/secret/data", server.url + "/other"]
        summary = engine.run(sources.memory(urls), out_dir=tmp_path)
        records = [
            orjson.loads(line)
            for line in (tmp_path / "worker-inproc.ndjson").read_bytes().splitlines()
            if line.strip()
        ]
        written_urls = {r["url"] for r in records}
        # /secret/... is disallowed by robots.txt and must not be fetched/kept.
        assert not any("/secret" in u for u in written_urls)
        assert any("/public" in u for u in written_urls)
        assert summary.metrics is not None


def test_robots_disabled_by_default_allows_all(tmp_path: Path) -> None:
    with EchoServer() as server:
        engine = Engine(EngineConfig(workers=1, chunk_size=5))  # respect_robots False
        urls = [server.url + "/public", server.url + "/secret/data"]
        summary = engine.run(sources.memory(urls), out_dir=tmp_path)
        assert summary.matched == 2  # both kept, robots not consulted
