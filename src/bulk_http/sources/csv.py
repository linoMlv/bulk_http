"""Streaming CSV/TSV sources with column mapping."""

from __future__ import annotations

import csv as _csv
import os
from collections.abc import Iterator, Mapping, Sequence

from bulk_http.models import Request
from bulk_http.sources._build import build_request
from bulk_http.sources.base import BaseSource

ColumnMapping = Mapping[str, "int | Sequence[int]"]


class CsvSource(BaseSource):
    """A source reading rows from a delimited file, mapping columns to fields.

    ``mapping`` links request attributes to zero-based column indices (e.g.
    ``{"url": 0, "needle": 1}``). The special key ``"keep"`` lists indices of
    columns to preserve as metadata; with ``has_header=True`` their header names
    are used as metadata keys, otherwise ``col<index>``.
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        mapping: ColumnMapping,
        *,
        delimiter: str = ",",
        has_header: bool = False,
        encoding: str = "utf-8",
    ) -> None:
        self._path = path
        self._mapping = mapping
        self._delimiter = delimiter
        self._has_header = has_header
        self._encoding = encoding

    def _requests(self) -> Iterator[Request]:
        keep_raw = self._mapping.get("keep")
        keep: list[int] = list(keep_raw) if isinstance(keep_raw, (list, tuple)) else []
        attr_map: dict[str, int] = {
            key: value
            for key, value in self._mapping.items()
            if key != "keep" and isinstance(value, int)
        }
        with open(self._path, newline="", encoding=self._encoding) as handle:
            reader = _csv.reader(handle, delimiter=self._delimiter)
            header: list[str] | None = next(reader, None) if self._has_header else None
            for row in reader:
                if not row:
                    continue
                fields: dict[str, str] = {}
                meta: dict[str, str] = {}
                try:
                    for attr, idx in attr_map.items():
                        fields[attr] = row[idx]
                    for idx in keep:
                        name = header[idx] if header is not None else f"col{idx}"
                        meta[name] = row[idx]
                except IndexError:
                    continue
                if not fields.get("url"):
                    continue
                yield build_request(dict(fields), meta)


def csv(
    path: str | os.PathLike[str],
    mapping: ColumnMapping,
    *,
    delimiter: str = ",",
    has_header: bool = False,
    encoding: str = "utf-8",
) -> CsvSource:
    """Build a streaming CSV source with the given column ``mapping``."""
    return CsvSource(path, mapping, delimiter=delimiter, has_header=has_header, encoding=encoding)


def tsv(
    path: str | os.PathLike[str],
    mapping: ColumnMapping,
    *,
    has_header: bool = False,
    encoding: str = "utf-8",
) -> CsvSource:
    """Build a streaming tab-separated source with the given column ``mapping``."""
    return CsvSource(path, mapping, delimiter="\t", has_header=has_header, encoding=encoding)
