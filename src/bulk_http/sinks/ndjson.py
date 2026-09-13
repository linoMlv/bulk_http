"""A per-worker NDJSON sink with buffered writes and durable commits."""

from __future__ import annotations

import os
from types import TracebackType

from bulk_http.models import Result
from bulk_http.sinks.serialize import result_to_line

_DEFAULT_FLUSH_BYTES = 64 * 1024


class NdjsonWorkerSink:
    """Append results to one NDJSON file, buffered, with durable commits.

    Results accumulate in memory and are flushed to the OS in large blocks. A
    :meth:`commit` flushes the buffer and ``fsync``s the file, returning the
    committed byte offset — the point up to which output is durable and to which
    the file must be truncated on resume.
    """

    def __init__(
        self, path: str | os.PathLike[str], *, flush_bytes: int = _DEFAULT_FLUSH_BYTES
    ) -> None:
        self._file = open(path, "ab")  # noqa: SIM115 - lifecycle managed by this sink
        self._buffer = bytearray()
        self._flush_bytes = flush_bytes

    def write(self, result: Result) -> None:
        self._buffer += result_to_line(result)
        if len(self._buffer) >= self._flush_bytes:
            self._flush_buffer()

    def _flush_buffer(self) -> None:
        if self._buffer:
            self._file.write(self._buffer)
            self._buffer.clear()

    def commit(self) -> int:
        """Flush and fsync, returning the durable byte offset."""
        self._flush_buffer()
        self._file.flush()
        os.fsync(self._file.fileno())
        return self._file.tell()

    def close(self) -> None:
        self._flush_buffer()
        self._file.close()

    def __enter__(self) -> NdjsonWorkerSink:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            self.commit()
        finally:
            self.close()
