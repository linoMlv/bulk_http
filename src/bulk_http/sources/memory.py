"""In-memory task source."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from bulk_http.models import Request
from bulk_http.sources.base import BaseSource


class MemorySource(BaseSource):
    """A source backed by an in-memory iterable of requests or URL strings."""

    def __init__(self, items: Iterable[Request | str]) -> None:
        self._items = items

    def _requests(self) -> Iterator[Request]:
        for item in self._items:
            yield item if isinstance(item, Request) else Request(url=item)


def memory(items: Iterable[Request | str]) -> MemorySource:
    """Build a source from an in-memory iterable of ``Request`` or URL strings."""
    return MemorySource(items)
