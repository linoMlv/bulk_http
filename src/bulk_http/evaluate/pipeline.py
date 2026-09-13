"""The full conditional-evaluation pipeline: status, patterns and predicate."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from bulk_http.decompress import decompress_fragment
from bulk_http.evaluate.context import build_context
from bulk_http.evaluate.patterns import PatternMatcher
from bulk_http.evaluate.status import status_matches
from bulk_http.models import EvalContext

Predicate = Callable[[EvalContext], bool]


def evaluate(
    *,
    status: int | None,
    url: str,
    headers: dict[str, str],
    fragment: bytes,
    content_encoding: str | None,
    matcher: PatternMatcher,
    expected_status: int | frozenset[int] | None = None,
    predicate: Predicate | None = None,
    meta: dict[str, Any] | None = None,
) -> tuple[bool, EvalContext | None]:
    """Decide whether a response matches, applying every configured condition.

    Conditions combine with AND: the expected status (if any), a needle hit (if
    the matcher is non-empty) and the predicate (if any) must all pass. With no
    condition configured, the response matches. Cheaper checks run first and
    short-circuit, so the predicate is only invoked on a decompressed, typed
    context when the earlier checks have passed. The context is returned only
    when a predicate is supplied.
    """
    if not status_matches(status, expected_status):
        return False, None

    decoded = decompress_fragment(fragment, content_encoding)

    if not matcher.is_empty and not matcher.search(decoded):
        return False, None

    if predicate is None:
        return True, None

    ctx = build_context(
        status=status if status is not None else 0,
        url=url,
        headers=headers,
        raw=decoded,
        meta=meta,
    )
    return bool(predicate(ctx)), ctx
