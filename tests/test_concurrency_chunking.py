"""Tests for chunking a task stream into bounded batches."""

from collections.abc import Iterator

import pytest

from bulk_http.concurrency import chunk_batches


def test_chunks_exact_multiple() -> None:
    assert list(chunk_batches(range(6), 2)) == [[0, 1], [2, 3], [4, 5]]


def test_last_batch_is_partial() -> None:
    assert list(chunk_batches(range(5), 2)) == [[0, 1], [2, 3], [4]]


def test_empty_iterable_yields_nothing() -> None:
    assert list(chunk_batches([], 3)) == []


def test_single_large_batch() -> None:
    assert list(chunk_batches(range(3), 10)) == [[0, 1, 2]]


def test_is_lazy_over_a_generator() -> None:
    def gen() -> Iterator[int]:
        yield from range(4)

    batches = chunk_batches(gen(), 2)
    assert next(batches) == [0, 1]
    assert next(batches) == [2, 3]


def test_invalid_size_rejected() -> None:
    with pytest.raises(ValueError):
        list(chunk_batches(range(3), 0))
