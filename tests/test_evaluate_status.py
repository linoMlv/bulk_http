"""Tests for HTTP status matching."""

from bulk_http.evaluate import status_matches


def test_none_expected_matches_any_status() -> None:
    assert status_matches(200, None) is True
    assert status_matches(500, None) is True


def test_int_expected_requires_equality() -> None:
    assert status_matches(200, 200) is True
    assert status_matches(301, 200) is False


def test_set_expected_checks_membership() -> None:
    assert status_matches(301, frozenset({200, 301})) is True
    assert status_matches(404, frozenset({200, 301})) is False


def test_status_none_never_matches_a_constraint() -> None:
    assert status_matches(None, 200) is False
    assert status_matches(None, frozenset({200})) is False
    assert status_matches(None, None) is True
