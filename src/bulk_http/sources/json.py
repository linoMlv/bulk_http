"""Streaming JSON Lines source.

Each line holds one JSON object describing a request. This keeps ingestion lazy
(one line at a time) for arbitrarily large inputs, unlike loading a whole JSON
array into memory.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import orjson

from bulk_http.models import Request
from bulk_http.sources._build import build_request
from bulk_http.sources.base import BaseSource


class JsonLinesSource(BaseSource):
    """A source reading one JSON object per line."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = path

    def _requests(self) -> Iterator[Request]:
        with open(self._path, "rb") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                obj: Any = orjson.loads(line)
                if not isinstance(obj, dict):
                    raise ValueError(f"each JSON line must be an object, got {type(obj).__name__}")
                yield build_request(dict(obj))


def json(path: str | os.PathLike[str]) -> JsonLinesSource:
    """Build a streaming source reading one JSON object per line from ``path``."""
    return JsonLinesSource(path)
