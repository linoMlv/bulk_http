"""Shared type aliases used across the package's public models."""

from __future__ import annotations

from typing import Literal

Method = Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
CutOn = Literal["wire", "decoded"]
HttpVersion = Literal["auto", "h1", "h2", "h3"]
AcceptEncoding = Literal["impersonate", "identity"]
CtxType = Literal["json", "html", "text"]

METHODS: frozenset[str] = frozenset(("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"))
IDEMPOTENT_METHODS: frozenset[str] = frozenset(("GET", "HEAD", "OPTIONS"))
CUT_ON_VALUES: frozenset[str] = frozenset(("wire", "decoded"))
HTTP_VERSIONS: frozenset[str] = frozenset(("auto", "h1", "h2", "h3"))
ACCEPT_ENCODINGS: frozenset[str] = frozenset(("impersonate", "identity"))
