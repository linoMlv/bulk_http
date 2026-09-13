"""Output sinks: durable per-worker NDJSON and exports."""

from __future__ import annotations

from bulk_http.sinks.ndjson import NdjsonWorkerSink
from bulk_http.sinks.serialize import result_to_line

__all__ = ["NdjsonWorkerSink", "result_to_line"]
