"""Build a Request from a loosely-typed field mapping (shared by file sources)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from bulk_http.models import Request

_STR_FIELDS = frozenset({"cut_on", "impersonate", "http_version", "accept_encoding", "proxy"})
_DICT_FIELDS = frozenset({"headers", "cookies"})
_INT_FIELDS = frozenset({"stream_cut", "max_redirects", "retries"})
_FLOAT_FIELDS = frozenset({"timeout", "total_timeout"})
_BOOL_FIELDS = frozenset({"fast_status", "verify_ssl", "follow_redirects", "retry_non_idempotent"})

_TRUE = frozenset({"1", "true", "yes", "y", "on"})
_FALSE = frozenset({"0", "false", "no", "n", "off", ""})


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def build_request(fields: dict[str, Any], meta: dict[str, Any] | None = None) -> Request:
    """Assemble a :class:`Request` from mapped ``fields``.

    Known keys populate the corresponding request field (with light type
    coercion so file sources can pass strings); ``needle``/``needles`` feed the
    search patterns; anything else — plus an explicit ``meta`` mapping — is
    preserved as metadata.
    """
    kwargs: dict[str, Any] = {}
    extra_meta: dict[str, Any] = dict(meta or {})
    needles: list[str] = []
    for key, value in fields.items():
        if key == "url":
            kwargs["url"] = str(value)
        elif key == "method":
            kwargs["method"] = str(value).upper()
        elif key in _STR_FIELDS:
            kwargs[key] = str(value)
        elif key in _DICT_FIELDS:
            kwargs[key] = dict(value)
        elif key in _INT_FIELDS:
            kwargs[key] = int(value)
        elif key in _FLOAT_FIELDS:
            kwargs[key] = float(value)
        elif key in _BOOL_FIELDS:
            kwargs[key] = _to_bool(value)
        elif key == "body":
            kwargs["body"] = value.encode() if isinstance(value, str) else bytes(value)
        elif key == "needle":
            needles.append(str(value))
        elif key == "needles":
            if isinstance(value, str):
                needles.append(value)
            elif isinstance(value, Iterable):
                needles.extend(str(v) for v in value)
            else:
                needles.append(str(value))
        elif key == "expected_status":
            if isinstance(value, (list, tuple, set, frozenset)):
                kwargs["expected_status"] = frozenset(int(v) for v in value)
            else:
                kwargs["expected_status"] = int(value)
        elif key == "meta":
            extra_meta.update(value)
        else:
            extra_meta[key] = value
    if needles:
        kwargs["needles"] = tuple(needles)
    if extra_meta:
        kwargs["meta"] = extra_meta
    return Request(**kwargs)
