"""Tests for allow/deny lists, identity header and authorization journal."""

from bulk_http.compliance import ComplianceFilter


def test_denylist_blocks_host() -> None:
    f = ComplianceFilter(denylist=["blocked.com"])
    assert f.is_allowed("https://blocked.com/x") is False
    assert f.is_allowed("https://ok.com/x") is True


def test_denylist_blocks_subdomains() -> None:
    f = ComplianceFilter(denylist=["blocked.com"])
    assert f.is_allowed("https://api.blocked.com/x") is False


def test_allowlist_restricts_to_listed_hosts() -> None:
    f = ComplianceFilter(allowlist=["ok.com"])
    assert f.is_allowed("https://ok.com/x") is True
    assert f.is_allowed("https://api.ok.com/x") is True
    assert f.is_allowed("https://other.com/x") is False


def test_empty_allowlist_allows_everything() -> None:
    f = ComplianceFilter()
    assert f.is_allowed("https://anything.com/x") is True


def test_denylist_takes_precedence_over_allowlist() -> None:
    f = ComplianceFilter(allowlist=["ok.com"], denylist=["ok.com"])
    assert f.is_allowed("https://ok.com/x") is False


def test_identity_header_injected_when_absent() -> None:
    f = ComplianceFilter(identity_header=("X-Contact", "team@example.com"))
    headers = f.apply_headers({"A": "b"})
    assert headers["X-Contact"] == "team@example.com"
    assert headers["A"] == "b"


def test_identity_header_does_not_override_existing() -> None:
    f = ComplianceFilter(identity_header=("X-Contact", "team@example.com"))
    headers = f.apply_headers({"X-Contact": "custom"})
    assert headers["X-Contact"] == "custom"


def test_apply_headers_without_identity_is_noop() -> None:
    f = ComplianceFilter()
    assert f.apply_headers({"A": "b"}) == {"A": "b"}
    assert f.apply_headers(None) == {}


def test_authorization_annotates_meta() -> None:
    f = ComplianceFilter(authorization="scope: bug-bounty ACME #123")
    meta = f.annotate_meta({"row": 1})
    assert meta["row"] == 1
    assert meta["authorization"] == "scope: bug-bounty ACME #123"


def test_no_authorization_leaves_meta_unchanged() -> None:
    f = ComplianceFilter()
    assert f.annotate_meta({"row": 1}) == {"row": 1}
