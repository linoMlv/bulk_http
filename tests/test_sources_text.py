"""Tests for the streaming text source."""

from pathlib import Path

from bulk_http import sources


def test_text_source_reads_one_url_per_line(tmp_path: Path) -> None:
    p = tmp_path / "urls.txt"
    p.write_text("https://a.com\nhttps://b.com\nhttps://c.com\n")
    tasks = list(sources.text(p))
    assert [t.request.url for t in tasks] == [
        "https://a.com",
        "https://b.com",
        "https://c.com",
    ]
    assert [t.source_id for t in tasks] == [0, 1, 2]


def test_text_source_skips_blank_lines_and_strips(tmp_path: Path) -> None:
    p = tmp_path / "urls.txt"
    p.write_text("  https://a.com  \n\n\nhttps://b.com\n   \n")
    tasks = list(sources.text(p))
    assert [t.request.url for t in tasks] == ["https://a.com", "https://b.com"]


def test_text_source_accepts_string_path(tmp_path: Path) -> None:
    p = tmp_path / "urls.txt"
    p.write_text("https://a.com\n")
    tasks = list(sources.text(str(p)))
    assert tasks[0].request.url == "https://a.com"


def test_text_source_honours_encoding(tmp_path: Path) -> None:
    p = tmp_path / "urls.txt"
    p.write_text("https://exämple.com/café\n", encoding="utf-8")
    tasks = list(sources.text(p, encoding="utf-8"))
    assert tasks[0].request.url == "https://exämple.com/café"
