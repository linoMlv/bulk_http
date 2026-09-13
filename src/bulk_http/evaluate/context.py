"""Build a typed EvalContext from a response's content type and fragment."""

from __future__ import annotations

from typing import Any

import orjson
from selectolax.parser import HTMLParser

from bulk_http._types import CtxType
from bulk_http.models import EvalContext


def _content_type(headers: dict[str, str]) -> str:
    for key, value in headers.items():
        if key.lower() == "content-type":
            return value.split(";", 1)[0].strip().lower()
    return ""


def _classify(mime: str) -> CtxType:
    if "json" in mime:
        return "json"
    if "html" in mime:
        return "html"
    return "text"


def build_context(
    *,
    status: int,
    url: str,
    headers: dict[str, str],
    raw: bytes,
    meta: dict[str, Any] | None = None,
) -> EvalContext:
    """Assemble the context passed to a user predicate.

    The content type selects the populated payload: JSON is deserialized via
    orjson (``None`` when the fragment is truncated/invalid), HTML is parsed into
    a selectolax DOM, and anything else is decoded as UTF-8 text. ``raw`` always
    holds the received (decompressed) fragment.
    """
    ctx_type = _classify(_content_type(headers))
    data: Any | None = None
    dom: Any | None = None
    text: str | None = None
    if ctx_type == "json":
        try:
            data = orjson.loads(raw)
        except orjson.JSONDecodeError:
            data = None
    elif ctx_type == "html":
        dom = HTMLParser(raw)
    else:
        text = raw.decode("utf-8", errors="replace")
    return EvalContext(
        type=ctx_type,
        status=status,
        url=url,
        headers=headers,
        meta=meta or {},
        raw=raw,
        data=data,
        dom=dom,
        text=text,
    )
