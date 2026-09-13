"""HTTP status-code matching."""

from __future__ import annotations


def status_matches(status: int | None, expected: int | frozenset[int] | None) -> bool:
    """Return whether ``status`` satisfies the ``expected`` constraint.

    ``None`` expected means "no constraint" (always matches). A missing status
    (transport error before a response) never satisfies an actual constraint.
    """
    if expected is None:
        return True
    if status is None:
        return False
    if isinstance(expected, int):
        return status == expected
    return status in expected
