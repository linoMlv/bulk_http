"""End-to-end resume of an interrupted campaign via its checkpoint."""

from collections.abc import Callable, Iterable
from pathlib import Path

import orjson

from bulk_http import Engine, sources
from bulk_http.checkpoint import CheckpointStore
from bulk_http.config import EngineConfig
from bulk_http.engine import ControlMessage
from bulk_http.models import Result, Task
from bulk_http.sinks import NdjsonWorkerSink

FILENAME = "worker-inproc.ndjson"
OnControl = Callable[[ControlMessage], None]
Batch = tuple[int, list[Task]]


class LimitedExecutor:
    """Commit at most ``limit`` batches, then optionally leave a torn write."""

    def __init__(self, out_dir: Path, *, limit: int, torn: bool = False) -> None:
        self._out_dir = out_dir
        self._limit = limit
        self._torn = torn

    def execute(self, batches: Iterable[Batch], on_control: OnControl) -> None:
        self._out_dir.mkdir(parents=True, exist_ok=True)
        path = self._out_dir / FILENAME
        sink = NdjsonWorkerSink(path)
        processed = 0
        try:
            for chunk_id, batch in batches:
                if processed >= self._limit:
                    break
                for task in batch:
                    sink.write(
                        Result(
                            source_id=task.source_id, url=task.request.url, status=200, matched=True
                        )
                    )
                offset = sink.commit()
                on_control(ControlMessage(chunk_id, FILENAME, offset, len(batch)))
                processed += 1
        finally:
            sink.close()
        if self._torn:
            with open(path, "ab") as handle:
                handle.write(b'{"source_id": 999, "url": "torn')


def _ids(path: Path) -> list[int]:
    return [
        orjson.loads(line)["source_id"] for line in path.read_bytes().splitlines() if line.strip()
    ]


def test_resume_skips_committed_and_replays_rest(tmp_path: Path) -> None:
    ckpt = tmp_path / "campaign.ckpt"
    config = EngineConfig(chunk_size=1, checkpoint=str(ckpt))
    urls = [f"https://a.com/{i}" for i in range(4)]

    # First run stops after 2 batches and leaves a torn partial write.
    first = Engine(config).run(
        sources.memory(urls),
        out_dir=tmp_path,
        executor=LimitedExecutor(tmp_path, limit=2, torn=True),
    )
    assert first.chunks == 2
    state = CheckpointStore(ckpt).load()
    assert set(state.committed) == {0, 1}

    # Second run resumes: truncates the torn line, skips 0 and 1, replays 2 and 3.
    second = Engine(config).run(
        sources.memory(urls), out_dir=tmp_path, executor=LimitedExecutor(tmp_path, limit=99)
    )
    assert second.chunks == 2  # only chunks 2 and 3 were processed
    ids = _ids(tmp_path / FILENAME)
    assert ids == [0, 1, 2, 3]
    assert len(ids) == len(set(ids))  # no duplicates, no torn line


def test_resume_with_empty_checkpoint_processes_all(tmp_path: Path) -> None:
    ckpt = tmp_path / "campaign.ckpt"
    config = EngineConfig(chunk_size=1, checkpoint=str(ckpt))
    summary = Engine(config).run(
        sources.memory(["https://a.com", "https://b.com"]),
        out_dir=tmp_path,
        executor=LimitedExecutor(tmp_path, limit=99),
    )
    assert summary.chunks == 2
