"""Tests for CSV/TSV sources with column mapping."""

from pathlib import Path

from bulk_http import sources


def test_csv_maps_url_and_needle_by_index(tmp_path: Path) -> None:
    p = tmp_path / "t.csv"
    p.write_text("https://a.com,admin\nhttps://b.com,root\n")
    tasks = list(sources.csv(p, mapping={"url": 0, "needle": 1}))
    assert [t.request.url for t in tasks] == ["https://a.com", "https://b.com"]
    assert tasks[0].request.needles == ("admin",)
    assert tasks[1].request.needles == ("root",)
    assert [t.source_id for t in tasks] == [0, 1]


def test_csv_keeps_metadata_columns(tmp_path: Path) -> None:
    p = tmp_path / "t.csv"
    p.write_text("https://a.com,admin,fr,42\n")
    tasks = list(sources.csv(p, mapping={"url": 0, "needle": 1, "keep": [2, 3]}))
    meta = tasks[0].request.meta
    assert meta["col2"] == "fr"
    assert meta["col3"] == "42"


def test_csv_with_header_uses_names_for_kept_columns(tmp_path: Path) -> None:
    p = tmp_path / "t.csv"
    p.write_text("target,term,lang,score\nhttps://a.com,admin,fr,42\n")
    tasks = list(sources.csv(p, mapping={"url": 0, "needle": 1, "keep": [2, 3]}, has_header=True))
    assert len(tasks) == 1
    meta = tasks[0].request.meta
    assert meta["lang"] == "fr"
    assert meta["score"] == "42"


def test_csv_custom_delimiter(tmp_path: Path) -> None:
    p = tmp_path / "t.csv"
    p.write_text("https://a.com;admin\n")
    tasks = list(sources.csv(p, mapping={"url": 0, "needle": 1}, delimiter=";"))
    assert tasks[0].request.needles == ("admin",)


def test_tsv_source(tmp_path: Path) -> None:
    p = tmp_path / "t.tsv"
    p.write_text("https://a.com\tadmin\n")
    tasks = list(sources.tsv(p, mapping={"url": 0, "needle": 1}))
    assert tasks[0].request.url == "https://a.com"
    assert tasks[0].request.needles == ("admin",)


def test_csv_maps_method_and_body(tmp_path: Path) -> None:
    p = tmp_path / "t.csv"
    p.write_text("https://a.com,POST,payload\n")
    tasks = list(sources.csv(p, mapping={"url": 0, "method": 1, "body": 2}))
    assert tasks[0].request.method == "POST"
    assert tasks[0].request.body == b"payload"


def test_csv_skips_short_rows_missing_url(tmp_path: Path) -> None:
    p = tmp_path / "t.csv"
    p.write_text("https://a.com,admin\n\nhttps://b.com,root\n")
    tasks = list(sources.csv(p, mapping={"url": 0, "needle": 1}))
    assert [t.request.url for t in tasks] == ["https://a.com", "https://b.com"]


def test_csv_skips_rows_too_short_for_mapping(tmp_path: Path) -> None:
    p = tmp_path / "t.csv"
    # Second row lacks the needle column referenced by the mapping.
    p.write_text("https://a.com,admin\nhttps://b.com\nhttps://c.com,root\n")
    tasks = list(sources.csv(p, mapping={"url": 0, "needle": 1}))
    assert [t.request.url for t in tasks] == ["https://a.com", "https://c.com"]


def test_csv_skips_rows_with_empty_url(tmp_path: Path) -> None:
    p = tmp_path / "t.csv"
    p.write_text(",admin\nhttps://b.com,root\n")
    tasks = list(sources.csv(p, mapping={"url": 0, "needle": 1}))
    assert [t.request.url for t in tasks] == ["https://b.com"]
