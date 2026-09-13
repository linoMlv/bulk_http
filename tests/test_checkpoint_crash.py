"""End-to-end resume under a simulated crash: zero loss, zero duplicates."""

from pathlib import Path

import orjson

from bulk_http.checkpoint import CheckpointStore, plan_resume, truncate_worker_files
from bulk_http.models import Result
from bulk_http.sinks import NdjsonWorkerSink


def _results(chunk: int) -> list[Result]:
    base = chunk * 2
    return [
        Result(source_id=base, url=f"https://a.com/{base}", status=200, matched=True),
        Result(source_id=base + 1, url=f"https://a.com/{base + 1}", status=200, matched=True),
    ]


def _source_ids(path: Path) -> list[int]:
    ids = []
    for raw in path.read_bytes().splitlines():
        if raw.strip():
            ids.append(orjson.loads(raw)["source_id"])
    return ids


def test_resume_after_crash_is_exactly_once(tmp_path: Path) -> None:
    worker_file = tmp_path / "w0.ndjson"
    ckpt = tmp_path / "campaign.ckpt"
    all_chunks = [0, 1, 2]

    # --- First run: commit chunk 0, then crash mid-writing chunk 1 ---
    store = CheckpointStore(ckpt)
    sink = NdjsonWorkerSink(worker_file)
    store.record_distributed(0)
    for result in _results(0):
        sink.write(result)
    offset0 = sink.commit()
    store.commit_chunk(0, "w0.ndjson", offset0, 2)

    store.record_distributed(1)
    for result in _results(1):
        sink.write(result)
    sink.commit()  # data may be flushed...
    # ...but simulate a crash before committing the chunk to the manifest, and a
    # further torn partial line landing on disk afterwards.
    sink.close()
    with open(worker_file, "ab") as handle:
        handle.write(b'{"source_id": 99, "url": "https://a.co')  # torn line
    store.close()

    # --- Recovery ---
    state = CheckpointStore(ckpt).load()
    plan = plan_resume(all_chunks, state)
    assert plan.to_replay == [1, 2]
    truncate_worker_files([worker_file], plan)
    # After truncation only chunk 0 survives; the torn line and uncommitted
    # chunk 1 are gone.
    assert _source_ids(worker_file) == [0, 1]

    # --- Second run: replay the pending/undistributed chunks ---
    store = CheckpointStore(ckpt)
    sink = NdjsonWorkerSink(worker_file)
    for chunk_id in plan.to_replay:
        store.record_distributed(chunk_id)
        for result in _results(chunk_id):
            sink.write(result)
        offset = sink.commit()
        store.commit_chunk(chunk_id, "w0.ndjson", offset, 2)
    sink.close()
    store.close()

    # Every source id exactly once, none lost, none duplicated.
    ids = _source_ids(worker_file)
    assert ids == [0, 1, 2, 3, 4, 5]
    assert len(ids) == len(set(ids))


def test_resume_with_no_progress_replays_everything(tmp_path: Path) -> None:
    ckpt = tmp_path / "campaign.ckpt"
    with CheckpointStore(ckpt) as store:
        store.record_distributed(0)
        store.record_distributed(1)
    state = CheckpointStore(ckpt).load()
    plan = plan_resume([0, 1, 2], state)
    assert plan.to_replay == [0, 1, 2]
    assert plan.truncations == {}
