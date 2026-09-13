"""Proxy management: pools, gateways, health tracking and rate limiting."""

from __future__ import annotations

from bulk_http.proxies.health import Outcome, ProxyHealth, classify_outcome

__all__ = ["Outcome", "ProxyHealth", "classify_outcome"]
