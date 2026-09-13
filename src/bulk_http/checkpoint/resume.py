"""Plan a crash-safe resume: which batches to replay and how to truncate output."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass

from bulk_http.checkpoint.store import CheckpointState


@dataclass(frozen=True, slots=True)
class ResumePlan:
    """What a resume must do: replay these chunks, truncate files to these offsets."""

    to_replay: list[int]
    truncations: dict[str, int]


def plan_resume(all_chunk_ids: Iterable[int], state: CheckpointState) -> ResumePlan:
    """Compute the resume plan for a campaign's full chunk id sequence.

    Any chunk that is not durably committed is replayed (distributed-but-pending
    plus never-distributed), and each worker file is truncated back to its last
    committed offset, discarding post-checkpoint partial writes.
    """
    to_replay = [chunk_id for chunk_id in all_chunk_ids if chunk_id not in state.committed]
    return ResumePlan(to_replay=to_replay, truncations=dict(state.committed_offsets))


def truncate_worker_files(paths: Iterable[str | os.PathLike[str]], plan: ResumePlan) -> None:
    """Truncate each worker file to its committed offset (0 if never committed)."""
    for path in paths:
        if not os.path.exists(path):
            continue
        offset = plan.truncations.get(os.path.basename(path), 0)
        with open(path, "ab") as handle:
            handle.truncate(offset)
