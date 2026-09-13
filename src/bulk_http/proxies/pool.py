"""A health-aware pool of proxies with round-robin selection."""

from __future__ import annotations

from bulk_http.proxies.health import Outcome, ProxyHealth


class ProxyPool:
    """Round-robin over a list of proxies, skipping quarantined ones.

    Each proxy has its own :class:`ProxyHealth`; :meth:`report` feeds outcomes
    back so unhealthy proxies drop out until their cooldown elapses. :meth:`select`
    returns the next available proxy, or ``None`` when none are available.
    """

    def __init__(
        self,
        proxies: list[str],
        *,
        window: int = 20,
        failure_threshold: float = 0.5,
        min_samples: int = 5,
        cooldown: float = 60.0,
        rate_limit_backoff: float = 30.0,
    ) -> None:
        self._proxies = list(proxies)
        self._health = {
            proxy: ProxyHealth(
                window=window,
                failure_threshold=failure_threshold,
                min_samples=min_samples,
                cooldown=cooldown,
                rate_limit_backoff=rate_limit_backoff,
            )
            for proxy in self._proxies
        }
        self._cursor = 0

    def select(self, *, now: float) -> str | None:
        for _ in range(len(self._proxies)):
            proxy = self._proxies[self._cursor]
            self._cursor = (self._cursor + 1) % len(self._proxies)
            if self._health[proxy].is_available(now=now):
                return proxy
        return None

    def report(self, proxy: str, outcome: Outcome, *, now: float) -> None:
        health = self._health.get(proxy)
        if health is not None:
            health.record(outcome, now=now)
