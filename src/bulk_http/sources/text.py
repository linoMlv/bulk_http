"""Streaming text source: one URL per line."""

from __future__ import annotations

import os
from collections.abc import Iterator

from bulk_http.models import Request
from bulk_http.sources.base import BaseSource


class TextSource(BaseSource):
    """A source reading one URL per line from a text file.

    Lines are read sequentially (never the whole file at once), stripped of
    surrounding whitespace, and blank lines are ignored.
    """

    def __init__(self, path: str | os.PathLike[str], *, encoding: str = "utf-8") -> None:
        self._path = path
        self._encoding = encoding

    def _requests(self) -> Iterator[Request]:
        with open(self._path, encoding=self._encoding) as handle:
            for line in handle:
                url = line.strip()
                if url:
                    yield Request(url=url)


def text(path: str | os.PathLike[str], *, encoding: str = "utf-8") -> TextSource:
    """Build a streaming source reading one URL per line from ``path``."""
    return TextSource(path, encoding=encoding)
