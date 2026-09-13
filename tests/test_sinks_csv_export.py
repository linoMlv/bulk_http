"""Tests for CSV export from NDJSON output."""

import csv as _csv
from pathlib import Path

from bulk_http.models import Result
from bulk_http.sinks import NdjsonWorkerSink, export_csv


def _write_ndjson(path: Path, results: list[Result]) -> None:
    with NdjsonWorkerSink(path) as sink:
        for result in results:
            sink.write(result)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="") as handle:
        return list(_csv.DictReader(handle))


def test_export_basic_fields(tmp_path: Path) -> None:
    src = tmp_path / "w0.ndjson"
    _write_ndjson(
        src,
        [
            Result(source_id=0, url="https://a.com", status=200, matched=True),
            Result(source_id=1, url="https://b.com", status=404, matched=False),
        ],
    )
    out = tmp_path / "out.csv"
    export_csv([src], out, columns=["source_id", "url", "status", "matched"])
    rows = _read_csv(out)
    assert rows[0]["url"] == "https://a.com"
    assert rows[0]["status"] == "200"
    assert rows[1]["matched"] == "False"


def test_export_infers_meta_columns(tmp_path: Path) -> None:
    src = tmp_path / "w0.ndjson"
    _write_ndjson(
        src,
        [Result(source_id=0, url="https://a.com", status=200, matched=True, meta={"lang": "fr"})],
    )
    out = tmp_path / "out.csv"
    export_csv([src], out)
    rows = _read_csv(out)
    assert rows[0]["lang"] == "fr"
    assert rows[0]["source_id"] == "0"


def test_export_merges_multiple_files(tmp_path: Path) -> None:
    a = tmp_path / "w0.ndjson"
    b = tmp_path / "w1.ndjson"
    _write_ndjson(a, [Result(source_id=0, url="https://a.com", status=200, matched=True)])
    _write_ndjson(b, [Result(source_id=1, url="https://b.com", status=200, matched=True)])
    out = tmp_path / "out.csv"
    export_csv([a, b], out, columns=["source_id", "url"])
    rows = _read_csv(out)
    assert {r["source_id"] for r in rows} == {"0", "1"}


def test_export_none_values_are_blank(tmp_path: Path) -> None:
    src = tmp_path / "w0.ndjson"
    _write_ndjson(
        src, [Result(source_id=0, url="https://a.com", status=None, matched=False, error="timeout")]
    )
    out = tmp_path / "out.csv"
    export_csv([src], out, columns=["status", "error"])
    rows = _read_csv(out)
    assert rows[0]["status"] == ""
    assert rows[0]["error"] == "timeout"


def test_export_returns_row_count(tmp_path: Path) -> None:
    src = tmp_path / "w0.ndjson"
    _write_ndjson(
        src,
        [
            Result(source_id=0, url="https://a.com", status=200, matched=True),
            Result(source_id=1, url="https://b.com", status=200, matched=True),
        ],
    )
    out = tmp_path / "out.csv"
    count = export_csv([src], out, columns=["source_id"])
    assert count == 2


def test_export_handles_blank_lines_and_repeated_meta_keys(tmp_path: Path) -> None:
    src = tmp_path / "w0.ndjson"
    _write_ndjson(
        src,
        [
            Result(source_id=0, url="https://a.com", status=200, matched=True, meta={"lang": "fr"}),
            Result(source_id=1, url="https://b.com", status=200, matched=True, meta={"lang": "en"}),
        ],
    )
    # Inject a stray blank line into the NDJSON file.
    with open(src, "ab") as handle:
        handle.write(b"\n")
    out = tmp_path / "out.csv"
    count = export_csv([src], out)
    rows = _read_csv(out)
    # "lang" appears once as a column despite being present on both rows.
    assert list(rows[0].keys()).count("lang") == 1
    assert count == 2
