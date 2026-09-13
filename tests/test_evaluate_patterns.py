"""Tests for the Aho-Corasick pattern matcher."""

from bulk_http.evaluate import PatternMatcher


def test_search_finds_single_pattern_in_text() -> None:
    m = PatternMatcher(("admin",))
    assert m.search("the admin panel") is True
    assert m.search("nothing here") is False


def test_search_multi_pattern() -> None:
    m = PatternMatcher(("admin", "root"))
    assert m.search("become root now") is True
    assert m.search("guest only") is False


def test_search_accepts_bytes_utf8() -> None:
    m = PatternMatcher(("café",))
    assert m.search("un café serré".encode()) is True


def test_search_tolerates_invalid_utf8_bytes() -> None:
    m = PatternMatcher(("admin",))
    assert m.search(b"\xff\xfeadmin\xff") is True


def test_find_returns_all_matches() -> None:
    m = PatternMatcher(("a", "ab"))
    found = m.find("xabx")
    assert set(found) == {"a", "ab"}


def test_empty_needles_matcher_reports_no_patterns() -> None:
    m = PatternMatcher(())
    assert m.is_empty is True
    assert m.search("anything") is False


def test_non_empty_matcher_reports_has_patterns() -> None:
    assert PatternMatcher(("x",)).is_empty is False


def test_find_on_empty_matcher_returns_empty_list() -> None:
    assert PatternMatcher(()).find("anything") == []
