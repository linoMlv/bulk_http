"""Convert committed NDJSON output into a single CSV file."""

from __future__ import annotations

import csv as _csv
import os
from collections.abc import Iterable, Iterator
from typing import Any

import orjson

_BASE_FIELDS = ("source_id", "url", "status", "matched", "error", "elapsed")


def _iter_records(paths: Iterable[str | os.PathLike[str]]) -> Iterator[dict[str, Any]]:
    for path in paths:
        with open(path, "rb") as handle:
            for raw in handle:
                line = raw.strip()
                if line:
                    yield orjson.loads(line)


def _value(record: dict[str, Any], column: str) -> Any:
    if column in _BASE_FIELDS:
        return record.get(column)
    return record.get("meta", {}).get(column)


def _infer_columns(paths: Iterable[str | os.PathLike[str]]) -> list[str]:
    meta_keys: list[str] = []
    seen: set[str] = set()
    for record in _iter_records(paths):
        for key in record.get("meta", {}):
            if key not in seen:
                seen.add(key)
                meta_keys.append(key)
    return [*_BASE_FIELDS, *meta_keys]


def export_csv(
    ndjson_paths: Iterable[str | os.PathLike[str]],
    csv_path: str | os.PathLike[str],
    *,
    columns: list[str] | None = None,
    delimiter: str = ",",
) -> int:
    """Write the NDJSON records to ``csv_path``; return the number of rows.

    Columns default to the base result fields plus every metadata key seen (a
    first pass collects them); ``None`` values become blank cells.
    """
    paths = list(ndjson_paths)
    resolved_columns = columns if columns is not None else _infer_columns(paths)
    rows = 0
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = _csv.writer(handle, delimiter=delimiter)
        writer.writerow(resolved_columns)
        for record in _iter_records(paths):
            writer.writerow(
                [
                    "" if (value := _value(record, col)) is None else value
                    for col in resolved_columns
                ]
            )
            rows += 1
    return rows
