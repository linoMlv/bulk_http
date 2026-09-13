"""Tests for Engine orchestration."""

from collections.abc import Callable
from pathlib import Path

import orjson

from bulk_http import Engine, Request, sinks, sources
from bulk_http.config import EngineConfig
from bulk_http.engine import InProcessExecutor
from bulk_http.net import FakeTransport, RawResponse


def _factory(fragment: bytes) -> Callable[[], FakeTransport]:
    def factory() -> FakeTransport:
        return FakeTransport.constant(RawResponse(status=200, url="u", fragment=fragment))

    return factory


def _executor(
    config: EngineConfig, out_dir: Path, fragment: bytes = b"the admin panel"
) -> InProcessExecutor:
    return InProcessExecutor(config, out_dir, transport_factory=_factory(fragment))


def test_public_api_exports() -> None:
    assert Engine is not None
    assert Request is not None
    assert hasattr(sources, "csv")
    assert hasattr(sinks, "NdjsonWorkerSink")


def test_run_writes_matched_results(tmp_path: Path) -> None:
    config = EngineConfig(chunk_size=2)
    engine = Engine(config)
    src = sources.memory(["https://a.com", "https://b.com", "https://c.com"])
    summary = engine.run(
        src,
        needle="admin",
        out_dir=tmp_path,
        executor=_executor(config, tmp_path),
    )
    assert summary.matched == 3
    assert summary.chunks == 2  # 3 urls / chunk_size 2


def test_run_records_distributed_and_commits_checkpoint(tmp_path: Path) -> None:
    ckpt = tmp_path / "campaign.ckpt"
    config = EngineConfig(chunk_size=1, checkpoint=str(ckpt))
    engine = Engine(config)
    engine.run(
        sources.memory(["https://a.com", "https://b.com"]),
        out_dir=tmp_path,
        executor=_executor(config, tmp_path),
    )
    from bulk_http.checkpoint import CheckpointStore

    state = CheckpointStore(ckpt).load()
    assert state.distributed == {0, 1}
    assert set(state.committed) == {0, 1}


def test_run_applies_denylist(tmp_path: Path) -> None:
    config = EngineConfig(chunk_size=10, denylist=("blocked.com",))
    engine = Engine(config)
    summary = engine.run(
        sources.memory(["https://ok.com", "https://blocked.com", "https://ok2.com"]),
        out_dir=tmp_path,
        executor=_executor(config, tmp_path, fragment=b"ok"),
    )
    assert summary.skipped == 1


def test_run_injects_identity_header_and_authorization(tmp_path: Path) -> None:
    config = EngineConfig(
        chunk_size=10,
        identity_header=("X-Contact", "team@example.com"),
        authorization="scope #7",
    )
    engine = Engine(config)
    # Echo the received headers into the fragment via a capturing transport.
    captured: list[dict[str, str] | None] = []

    def factory() -> FakeTransport:
        def responder(resolved: object, attempt: int) -> RawResponse:
            captured.append(resolved.headers)  # type: ignore[attr-defined]
            return RawResponse(status=200, url="u", fragment=b"x")

        return FakeTransport(responder)

    executor = InProcessExecutor(config, tmp_path, transport_factory=factory)
    engine.run(
        sources.memory(["https://a.com"]),
        out_dir=tmp_path,
        executor=executor,
    )
    assert captured[0] is not None
    assert captured[0]["X-Contact"] == "team@example.com"
    # authorization is attached to output metadata (written when matched); here
    # not matched, so assert via a matched run instead:
    summary = engine.run(
        sources.memory([Request(url="https://a.com", needles=("x",))]),
        out_dir=tmp_path / "auth",
        executor=InProcessExecutor(
            config, tmp_path / "auth", transport_factory=_factory(b"x here")
        ),
    )
    line = (tmp_path / "auth" / "worker-inproc.ndjson").read_bytes().splitlines()[0]
    assert orjson.loads(line)["meta"]["authorization"] == "scope #7"
    assert summary.matched == 1


def test_engine_exposes_config() -> None:
    config = EngineConfig(chunk_size=5)
    assert Engine(config).config is config


def test_engine_builds_config_from_kwargs() -> None:
    engine = Engine(chunk_size=7, impersonate="firefox")
    assert engine.config.chunk_size == 7
    assert engine.config.impersonate == "firefox"
