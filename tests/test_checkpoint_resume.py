"""Tests for resume planning and crash-safe truncation."""

from pathlib import Path

from bulk_http.checkpoint import (
    CheckpointState,
    CheckpointStore,
    plan_resume,
    truncate_worker_files,
)


def _state_with(
    tmp_path: Path,
    entries: list[tuple[int, str, int, int]],
    distributed: list[int],
) -> CheckpointState:
    path = tmp_path / "campaign.ckpt"
    with CheckpointStore(path) as store:
        for cid in distributed:
            store.record_distributed(cid)
        for cid, file, offset, count in entries:
            store.commit_chunk(cid, file, offset, count)
    return CheckpointStore(path).load()


def test_replays_uncommitted_chunks(tmp_path: Path) -> None:
    state = _state_with(tmp_path, [(0, "w0.ndjson", 100, 5)], distributed=[0, 1, 2])
    plan = plan_resume([0, 1, 2, 3], state)
    # 0 committed; 1,2 distributed-not-committed; 3 never distributed.
    assert plan.to_replay == [1, 2, 3]


def test_truncations_reflect_committed_offsets(tmp_path: Path) -> None:
    state = _state_with(
        tmp_path,
        [(0, "w0.ndjson", 250, 5), (1, "w1.ndjson", 80, 3)],
        distributed=[0, 1],
    )
    plan = plan_resume([0, 1], state)
    assert plan.truncations == {"w0.ndjson": 250, "w1.ndjson": 80}


def test_truncate_worker_files_removes_post_checkpoint_bytes(tmp_path: Path) -> None:
    wf = tmp_path / "w0.ndjson"
    wf.write_bytes(b"committed-line\n" + b"partial-uncommitted")
    committed_len = len(b"committed-line\n")
    state = _state_with(tmp_path, [(0, "w0.ndjson", committed_len, 1)], distributed=[0])
    plan = plan_resume([0], state)
    truncate_worker_files([wf], plan)
    assert wf.read_bytes() == b"committed-line\n"


def test_truncate_file_without_commit_is_emptied(tmp_path: Path) -> None:
    wf = tmp_path / "w9.ndjson"
    wf.write_bytes(b"all-uncommitted\n")
    state = _state_with(tmp_path, [], distributed=[0])
    plan = plan_resume([0], state)
    truncate_worker_files([wf], plan)
    assert wf.read_bytes() == b""


def test_truncate_missing_file_is_ignored(tmp_path: Path) -> None:
    state = _state_with(tmp_path, [], distributed=[])
    plan = plan_resume([], state)
    truncate_worker_files([tmp_path / "absent.ndjson"], plan)  # must not raise


def test_nothing_to_replay_when_all_committed(tmp_path: Path) -> None:
    state = _state_with(tmp_path, [(0, "w0.ndjson", 10, 1)], distributed=[0])
    plan = plan_resume([0], state)
    assert plan.to_replay == []
