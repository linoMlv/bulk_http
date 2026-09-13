"""Lazy input sources that stream :class:`~bulk_http.models.Task` objects."""

from __future__ import annotations

from bulk_http.sources.base import BaseSource
from bulk_http.sources.csv import csv, tsv
from bulk_http.sources.memory import memory
from bulk_http.sources.text import text

__all__ = ["BaseSource", "csv", "memory", "text", "tsv"]
