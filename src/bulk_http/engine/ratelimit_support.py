"""Build the rate limiter an executor should use from the engine config."""

from __future__ import annotations

from bulk_http.concurrency.processor import RateLimiter
from bulk_http.config import EngineConfig
from bulk_http.proxies import AdaptiveRateLimiter, DomainRateLimiter


def build_rate_limiter(config: EngineConfig) -> RateLimiter | None:
    """Adaptive limiter if configured, else a fixed-rate one, else none."""
    if config.adaptive_rate is not None:
        return AdaptiveRateLimiter(config.adaptive_rate)
    if config.per_domain_rate_limit is not None:
        return DomainRateLimiter(config.per_domain_rate_limit)
    return None
