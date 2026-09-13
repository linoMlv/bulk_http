"""Proxy management: pools, gateways, health tracking and rate limiting."""

from __future__ import annotations

from bulk_http.proxies.backconnect import BackconnectGateway
from bulk_http.proxies.health import Outcome, ProxyHealth, classify_outcome
from bulk_http.proxies.pool import ProxyPool
from bulk_http.proxies.ratelimit import DomainRateLimiter

__all__ = [
    "BackconnectGateway",
    "DomainRateLimiter",
    "Outcome",
    "ProxyHealth",
    "ProxyPool",
    "classify_outcome",
]
