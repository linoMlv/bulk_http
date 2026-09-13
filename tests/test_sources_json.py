"""Tests for the streaming JSON Lines source."""

from pathlib import Path

import pytest

from bulk_http import sources


def test_json_lines_basic(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    p.write_text(
        '{"url": "https://a.com", "needle": "admin"}\n{"url": "https://b.com", "method": "post"}\n'
    )
    tasks = list(sources.json(p))
    assert [t.request.url for t in tasks] == ["https://a.com", "https://b.com"]
    assert tasks[0].request.needles == ("admin",)
    assert tasks[1].request.method == "POST"
    assert [t.source_id for t in tasks] == [0, 1]


def test_json_lines_skips_blank_lines(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    p.write_text('{"url": "https://a.com"}\n\n\n{"url": "https://b.com"}\n')
    tasks = list(sources.json(p))
    assert [t.request.url for t in tasks] == ["https://a.com", "https://b.com"]


def test_json_lines_unknown_keys_become_metadata(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    p.write_text('{"url": "https://a.com", "campaign": "x", "score": 5}\n')
    meta = next(iter(sources.json(p))).request.meta
    assert meta == {"campaign": "x", "score": 5}


def test_json_lines_supports_typed_fields(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    p.write_text(
        '{"url": "https://a.com", "headers": {"A": "b"}, "needles": ["x", "y"], '
        '"stream_cut": 2048, "fast_status": true}\n'
    )
    req = next(iter(sources.json(p))).request
    assert req.headers == {"A": "b"}
    assert req.needles == ("x", "y")
    assert req.stream_cut == 2048
    assert req.fast_status is True


def test_json_lines_rejects_non_object_line(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    p.write_text('["not", "an", "object"]\n')
    with pytest.raises(ValueError):
        list(sources.json(p))


def test_json_lines_accepts_string_path(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    p.write_text('{"url": "https://a.com"}\n')
    assert next(iter(sources.json(str(p)))).request.url == "https://a.com"
