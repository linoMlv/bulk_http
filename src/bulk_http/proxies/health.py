"""Proxy outcome classification and a per-proxy circuit breaker."""

from __future__ import annotations

from collections import deque
from typing import Literal

from bulk_http.net.transport import RawResponse

Outcome = Literal["ok", "transport_error", "rate_limited", "origin_error"]


def classify_outcome(response: RawResponse) -> Outcome:
    """Classify a response for proxy-health accounting.

    Transport failures and proxy auth (407) count against the proxy; 429 asks for
    a backoff rather than quarantine; origin statuses (403, 5xx) are blamed on the
    target, not the proxy; everything else is a success.
    """
    if response.error is not None:
        return "transport_error"
    status = response.status
    if status == 407:
        return "transport_error"
    if status == 429:
        return "rate_limited"
    if status == 403 or (status is not None and 500 <= status < 600):
        return "origin_error"
    return "ok"


class ProxyHealth:
    """A sliding-window circuit breaker for a single proxy.

    Only transport-related outcomes (``ok`` and ``transport_error``) feed the
    window; once at least ``min_samples`` are seen and the failure rate reaches
    ``failure_threshold``, the proxy is quarantined for ``cooldown`` seconds. A
    ``rate_limited`` outcome triggers a shorter backoff instead of quarantine.
    """

    __slots__ = (
        "_backoff_until",
        "_cooldown",
        "_failure_threshold",
        "_min_samples",
        "_quarantined_until",
        "_rate_limit_backoff",
        "_window",
    )

    def __init__(
        self,
        *,
        window: int = 20,
        failure_threshold: float = 0.5,
        min_samples: int = 5,
        cooldown: float = 60.0,
        rate_limit_backoff: float = 30.0,
    ) -> None:
        self._window: deque[bool] = deque(maxlen=window)
        self._failure_threshold = failure_threshold
        self._min_samples = min_samples
        self._cooldown = cooldown
        self._rate_limit_backoff = rate_limit_backoff
        self._quarantined_until = 0.0
        self._backoff_until = 0.0

    def record(self, outcome: Outcome, *, now: float) -> None:
        if outcome == "rate_limited":
            self._backoff_until = now + self._rate_limit_backoff
            return
        if outcome not in ("ok", "transport_error"):
            return
        self._window.append(outcome == "transport_error")
        if len(self._window) < self._min_samples:
            return
        failures = sum(1 for failed in self._window if failed)
        if failures / len(self._window) >= self._failure_threshold:
            self._quarantined_until = now + self._cooldown
            self._window.clear()

    def is_available(self, *, now: float) -> bool:
        return now >= self._quarantined_until and now >= self._backoff_until
