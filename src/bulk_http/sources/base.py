"""Base machinery shared by all lazy task sources."""

from __future__ import annotations

import abc
from collections.abc import Iterator

from bulk_http.models import Request, Task


class BaseSource(abc.ABC):
    """A lazy, re-iterable stream of :class:`Task` objects.

    Subclasses yield :class:`Request` objects from :meth:`_requests`; the base
    assigns a monotonic ``source_id`` (the idempotency key) in read order. Each
    call to ``iter()`` restarts the underlying stream so a source can be
    consumed more than once when its backing store allows it.
    """

    @abc.abstractmethod
    def _requests(self) -> Iterator[Request]:
        """Yield the requests of this source in a deterministic order."""
        raise NotImplementedError  # pragma: no cover

    def __iter__(self) -> Iterator[Task]:
        for source_id, request in enumerate(self._requests()):
            yield Task(source_id=source_id, request=request)
