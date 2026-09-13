"""Tests for the Result and EvalContext models."""

from dataclasses import FrozenInstanceError

import pytest

from bulk_http.models import EvalContext, Result


def test_result_holds_outcome_fields() -> None:
    res = Result(
        source_id=5,
        url="https://example.com",
        status=200,
        matched=True,
        data={"title": "Home"},
        meta={"row": 5},
    )
    assert res.source_id == 5
    assert res.status == 200
    assert res.matched is True
    assert res.data == {"title": "Home"}
    assert res.error is None
    assert res.elapsed is None


def test_result_supports_transport_error_without_status() -> None:
    res = Result(
        source_id=1,
        url="https://example.com",
        status=None,
        matched=False,
        error="connect_timeout",
        elapsed=2.5,
    )
    assert res.status is None
    assert res.error == "connect_timeout"
    assert res.elapsed == 2.5


def test_result_is_frozen() -> None:
    res = Result(source_id=1, url="u", status=None, matched=False)
    with pytest.raises(FrozenInstanceError):
        res.matched = True  # type: ignore[misc]


def test_eval_context_exposes_typed_payload_fields() -> None:
    ctx = EvalContext(
        type="text",
        status=200,
        url="https://example.com",
        headers={"content-type": "text/plain"},
        meta={"row": 1},
        raw=b"hello",
        text="hello",
    )
    assert ctx.type == "text"
    assert ctx.text == "hello"
    assert ctx.data is None
    assert ctx.dom is None
    assert ctx.headers["content-type"] == "text/plain"


def test_eval_context_rejects_unknown_type() -> None:
    with pytest.raises(ValueError):
        EvalContext(
            type="xml",  # type: ignore[arg-type]
            status=200,
            url="u",
            headers={},
            meta={},
            raw=b"",
        )
