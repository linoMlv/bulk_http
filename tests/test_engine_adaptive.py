"""Adaptive rate limiting wired through the engine, incl. ban -> stop."""

from collections.abc import Callable
from pathlib import Path

import pytest

from bulk_http import Engine, sources
from bulk_http.config import EngineConfig
from bulk_http.engine import InProcessExecutor
from bulk_http.net import FakeTransport, RawResponse
from bulk_http.proxies import AdaptiveRateConfig, AdaptiveRateLimiter, BanSuspectedError


def test_default_executor_uses_adaptive_limiter_when_configured(tmp_path: Path) -> None:
    engine = Engine(EngineConfig(workers=1, adaptive_rate=AdaptiveRateConfig()))
    executor = engine._default_executor(tmp_path, None, proxies=None)
    assert isinstance(executor._rate_limiter, AdaptiveRateLimiter)  # type: ignore[attr-defined]


def test_adaptive_takes_precedence_over_fixed_rate(tmp_path: Path) -> None:
    engine = Engine(
        EngineConfig(workers=1, per_domain_rate_limit=5.0, adaptive_rate=AdaptiveRateConfig())
    )
    executor = engine._default_executor(tmp_path, None, proxies=None)
    assert isinstance(executor._rate_limiter, AdaptiveRateLimiter)  # type: ignore[attr-defined]


def _error_factory() -> Callable[[], FakeTransport]:
    def factory() -> FakeTransport:
        return FakeTransport.constant(RawResponse(status=None, url="u", error="ConnectionError"))

    return factory


def test_persistent_failures_stop_the_campaign_with_ban_error(tmp_path: Path) -> None:
    # High, fixed rate -> negligible pacing; tiny ban window -> stops quickly.
    cfg = EngineConfig(
        workers=1,
        chunk_size=10,
        adaptive_rate=AdaptiveRateConfig(
            start_rate=1000.0, min_rate=1000.0, max_rate=1000.0, ban_window=3, ban_failures=3
        ),
    )
    executor = InProcessExecutor(
        cfg,
        tmp_path,
        transport_factory=_error_factory(),
        rate_limiter=AdaptiveRateLimiter(cfg.adaptive_rate),  # type: ignore[arg-type]
    )
    urls = [f"https://a.com/{i}" for i in range(6)]
    with pytest.raises(BanSuspectedError):
        Engine(cfg).run(sources.memory(urls), out_dir=tmp_path, executor=executor)
