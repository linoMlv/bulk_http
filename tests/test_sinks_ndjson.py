"""Tests for the per-worker NDJSON sink."""

from pathlib import Path

import orjson

from bulk_http.models import Result
from bulk_http.sinks import NdjsonWorkerSink


def _result(sid: int, **kw: object) -> Result:
    base = {"source_id": sid, "url": f"https://a.com/{sid}", "status": 200, "matched": True}
    base.update(kw)
    return Result(**base)  # type: ignore[arg-type]


def test_writes_one_json_line_per_result(tmp_path: Path) -> None:
    path = tmp_path / "w0.ndjson"
    sink = NdjsonWorkerSink(path)
    sink.write(_result(0))
    sink.write(_result(1, meta={"row": 1}))
    sink.commit()
    sink.close()
    lines = path.read_bytes().splitlines()
    assert len(lines) == 2
    first = orjson.loads(lines[0])
    assert first["source_id"] == 0
    assert first["url"] == "https://a.com/0"
    assert first["matched"] is True


def test_commit_returns_byte_offset(tmp_path: Path) -> None:
    path = tmp_path / "w0.ndjson"
    sink = NdjsonWorkerSink(path)
    sink.write(_result(0))
    offset = sink.commit()
    sink.close()
    assert offset == path.stat().st_size
    assert offset > 0


def test_commit_is_monotonic(tmp_path: Path) -> None:
    path = tmp_path / "w0.ndjson"
    sink = NdjsonWorkerSink(path)
    sink.write(_result(0))
    first = sink.commit()
    sink.write(_result(1))
    second = sink.commit()
    sink.close()
    assert second > first


def test_result_fields_are_serialized(tmp_path: Path) -> None:
    path = tmp_path / "w0.ndjson"
    sink = NdjsonWorkerSink(path)
    sink.write(
        _result(5, status=None, matched=False, error="timeout", elapsed=1.5, meta={"k": "v"})
    )
    sink.commit()
    sink.close()
    record = orjson.loads(path.read_bytes().splitlines()[0])
    assert record["status"] is None
    assert record["error"] == "timeout"
    assert record["elapsed"] == 1.5
    assert record["meta"] == {"k": "v"}


def test_context_manager_commits_and_closes(tmp_path: Path) -> None:
    path = tmp_path / "w0.ndjson"
    with NdjsonWorkerSink(path) as sink:
        sink.write(_result(0))
    assert path.stat().st_size > 0


def test_buffer_flushes_automatically_at_threshold(tmp_path: Path) -> None:
    path = tmp_path / "w0.ndjson"
    # A tiny threshold forces the internal buffer to flush on every write.
    sink = NdjsonWorkerSink(path, flush_bytes=10)
    sink.write(_result(0))
    sink.write(_result(1))
    sink.commit()
    sink.close()
    assert len(path.read_bytes().splitlines()) == 2
