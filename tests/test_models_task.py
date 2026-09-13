"""Tests for the Task model (a source-identified request unit)."""

import pickle
from dataclasses import FrozenInstanceError

import pytest

from bulk_http.models import Request, Task


def test_task_wraps_request_with_source_id() -> None:
    req = Request(url="https://example.com", needles=("x",))
    task = Task(source_id=7, request=req)
    assert task.source_id == 7
    assert task.request is req


def test_task_is_frozen() -> None:
    task = Task(source_id=1, request=Request(url="https://example.com"))
    with pytest.raises(FrozenInstanceError):
        task.source_id = 2  # type: ignore[misc]


def test_task_survives_pickle_round_trip() -> None:
    # spawn-based multiprocessing requires tasks to be picklable.
    req = Request(
        url="https://example.com",
        method="POST",
        headers={"A": "b"},
        body=b"data",
        needles=("admin",),
        meta={"row": 3},
    )
    task = Task(source_id=99, request=req)
    restored = pickle.loads(pickle.dumps(task))
    assert restored == task
    assert restored.request.body == b"data"
    assert restored.request.meta == {"row": 3}


def test_task_rejects_negative_source_id() -> None:
    with pytest.raises(ValueError):
        Task(source_id=-1, request=Request(url="https://example.com"))
