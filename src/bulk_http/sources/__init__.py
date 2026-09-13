"""Lazy input sources that stream :class:`~bulk_http.models.Task` objects."""

from __future__ import annotations

from bulk_http.sources.base import BaseSource
from bulk_http.sources.memory import memory

__all__ = ["BaseSource", "memory"]
