"""Tests for the transactional per-batch checkpoint store."""

from pathlib import Path

from bulk_http.checkpoint import CheckpointStore


def test_records_distributed_chunks(tmp_path: Path) -> None:
    path = tmp_path / "campaign.ckpt"
    with CheckpointStore(path) as store:
        store.record_distributed(0)
        store.record_distributed(1)
    state = CheckpointStore(path).load()
    assert state.distributed == {0, 1}
    assert state.committed == {}


def test_commit_chunk_records_offset_and_count(tmp_path: Path) -> None:
    path = tmp_path / "campaign.ckpt"
    with CheckpointStore(path) as store:
        store.record_distributed(0)
        store.commit_chunk(0, "w0.ndjson", 128, 10)
    state = CheckpointStore(path).load()
    assert 0 in state.committed
    assert state.committed[0].worker_file == "w0.ndjson"
    assert state.committed[0].offset == 128
    assert state.committed[0].count == 10


def test_committed_offset_per_file_is_the_latest(tmp_path: Path) -> None:
    path = tmp_path / "campaign.ckpt"
    with CheckpointStore(path) as store:
        store.commit_chunk(0, "w0.ndjson", 100, 5)
        store.commit_chunk(1, "w0.ndjson", 250, 5)
        store.commit_chunk(2, "w1.ndjson", 80, 3)
    state = CheckpointStore(path).load()
    assert state.committed_offsets == {"w0.ndjson": 250, "w1.ndjson": 80}


def test_pending_chunks_are_distributed_but_not_committed(tmp_path: Path) -> None:
    path = tmp_path / "campaign.ckpt"
    with CheckpointStore(path) as store:
        store.record_distributed(0)
        store.record_distributed(1)
        store.commit_chunk(0, "w0.ndjson", 50, 2)
    state = CheckpointStore(path).load()
    assert state.pending() == {1}


def test_load_ignores_trailing_truncated_line(tmp_path: Path) -> None:
    path = tmp_path / "campaign.ckpt"
    with CheckpointStore(path) as store:
        store.commit_chunk(0, "w0.ndjson", 100, 5)
    # Simulate a crash mid-write appending a truncated (invalid) JSON line.
    with open(path, "ab") as handle:
        handle.write(b'{"type": "committed", "chunk_id": 1, "worker')
    state = CheckpointStore(path).load()
    assert set(state.committed) == {0}


def test_load_on_missing_file_is_empty(tmp_path: Path) -> None:
    state = CheckpointStore(tmp_path / "none.ckpt").load()
    assert state.distributed == set()
    assert state.committed == {}


def test_load_skips_blank_and_unknown_entries(tmp_path: Path) -> None:
    path = tmp_path / "campaign.ckpt"
    with CheckpointStore(path) as store:
        store.commit_chunk(0, "w0.ndjson", 100, 5)
    with open(path, "ab") as handle:
        handle.write(b"\n")  # blank line
        handle.write(b'{"type": "note", "msg": "ignored"}\n')  # unknown type
    state = CheckpointStore(path).load()
    assert set(state.committed) == {0}
