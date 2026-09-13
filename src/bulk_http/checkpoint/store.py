"""Transactional per-batch checkpointing via an append-only manifest."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from types import TracebackType

import orjson


@dataclass(frozen=True, slots=True)
class CommittedChunk:
    """A durably-committed batch: its worker file, byte offset and result count."""

    chunk_id: int
    worker_file: str
    offset: int
    count: int


@dataclass(frozen=True, slots=True)
class CheckpointState:
    """The reconstructed checkpoint: what was distributed and what committed."""

    distributed: set[int] = field(default_factory=set)
    committed: dict[int, CommittedChunk] = field(default_factory=dict)
    committed_offsets: dict[str, int] = field(default_factory=dict)

    def pending(self) -> set[int]:
        """Chunks that were handed out but never committed (must be replayed)."""
        return self.distributed - set(self.committed)


class CheckpointStore:
    """Append-only manifest recording distributed and committed batches.

    Each committed batch appends one entry that is ``fsync``ed, so on resume the
    committed offsets tell exactly how far each worker file is durable. The caller
    must flush+fsync the worker file (obtaining its offset) *before* calling
    :meth:`commit_chunk` — output is made durable before the checkpoint advances.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = path
        self._file = open(path, "ab")  # noqa: SIM115 - lifecycle managed by this store

    def _append(self, entry: dict[str, object]) -> None:
        self._file.write(orjson.dumps(entry) + b"\n")
        self._file.flush()
        os.fsync(self._file.fileno())

    def record_distributed(self, chunk_id: int) -> None:
        self._append({"type": "distributed", "chunk_id": chunk_id})

    def commit_chunk(self, chunk_id: int, worker_file: str, offset: int, count: int) -> None:
        self._append(
            {
                "type": "committed",
                "chunk_id": chunk_id,
                "worker_file": worker_file,
                "offset": offset,
                "count": count,
            }
        )

    def load(self) -> CheckpointState:
        state = CheckpointState()
        with open(self._path, "rb") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                try:
                    entry = orjson.loads(line)
                except orjson.JSONDecodeError:
                    continue  # trailing truncated line from a crash: ignore
                if entry.get("type") == "distributed":
                    state.distributed.add(entry["chunk_id"])
                elif entry.get("type") == "committed":
                    chunk = CommittedChunk(
                        chunk_id=entry["chunk_id"],
                        worker_file=entry["worker_file"],
                        offset=entry["offset"],
                        count=entry["count"],
                    )
                    state.distributed.add(chunk.chunk_id)
                    state.committed[chunk.chunk_id] = chunk
                    state.committed_offsets[chunk.worker_file] = chunk.offset
        return state

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> CheckpointStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
