"""Tests for the in-memory source and the Source contract."""

from collections.abc import Iterator

from bulk_http import sources
from bulk_http.models import Request, Task


def test_memory_source_yields_tasks_with_monotonic_ids() -> None:
    src = sources.memory(
        [
            Request(url="https://a.com"),
            Request(url="https://b.com"),
        ]
    )
    tasks = list(src)
    assert all(isinstance(t, Task) for t in tasks)
    assert [t.source_id for t in tasks] == [0, 1]
    assert [t.request.url for t in tasks] == ["https://a.com", "https://b.com"]


def test_memory_source_accepts_bare_url_strings() -> None:
    src = sources.memory(["https://a.com", "https://b.com"])
    tasks = list(src)
    assert [t.request.url for t in tasks] == ["https://a.com", "https://b.com"]
    assert tasks[0].request.method == "GET"


def test_memory_source_is_iterable_and_lazy() -> None:
    src = sources.memory(["https://a.com"])
    it = iter(src)
    assert isinstance(it, Iterator)
    first = next(it)
    assert first.source_id == 0


def test_memory_source_can_be_iterated_twice() -> None:
    src = sources.memory(["https://a.com", "https://b.com"])
    assert [t.request.url for t in src] == ["https://a.com", "https://b.com"]
    assert [t.source_id for t in src] == [0, 1]
