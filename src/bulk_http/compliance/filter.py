"""Compliance guardrails: allow/deny lists, identity header, authorization note."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit


def _host_matches(host: str, entry: str) -> bool:
    return host == entry or host.endswith("." + entry)


class ComplianceFilter:
    """Apply domain allow/deny, an identity header and an authorization note.

    A denylist entry blocks a host and its subdomains; a non-empty allowlist
    restricts to listed hosts (and their subdomains); deny takes precedence. The
    identity header is added when absent, and the authorization note is attached
    to output metadata for traceability.
    """

    def __init__(
        self,
        *,
        allowlist: Iterable[str] | None = None,
        denylist: Iterable[str] | None = None,
        identity_header: tuple[str, str] | None = None,
        authorization: str | None = None,
    ) -> None:
        self._allowlist = list(allowlist or [])
        self._denylist = list(denylist or [])
        self._identity_header = identity_header
        self._authorization = authorization

    def is_allowed(self, url: str) -> bool:
        host = urlsplit(url).hostname or ""
        if any(_host_matches(host, entry) for entry in self._denylist):
            return False
        if self._allowlist:
            return any(_host_matches(host, entry) for entry in self._allowlist)
        return True

    def apply_headers(self, headers: dict[str, str] | None) -> dict[str, str]:
        result = dict(headers or {})
        if self._identity_header is not None:
            name, value = self._identity_header
            if not any(key.lower() == name.lower() for key in result):
                result[name] = value
        return result

    def annotate_meta(self, meta: dict[str, Any]) -> dict[str, Any]:
        if self._authorization is None:
            return meta
        annotated = dict(meta)
        annotated["authorization"] = self._authorization
        return annotated
