"""Serialize a Result to a single NDJSON line."""

from __future__ import annotations

import orjson

from bulk_http.models import Result


def result_to_line(result: Result) -> bytes:
    """Serialize ``result`` as one newline-terminated JSON object."""
    payload = {
        "source_id": result.source_id,
        "url": result.url,
        "status": result.status,
        "matched": result.matched,
        "data": result.data,
        "meta": result.meta,
        "error": result.error,
        "elapsed": result.elapsed,
    }
    return orjson.dumps(payload) + b"\n"
