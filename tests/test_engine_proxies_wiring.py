"""Tests that the engine wires a proxy pool and per-domain rate limit."""

from pathlib import Path

from bulk_http import Engine
from bulk_http.config import EngineConfig
from bulk_http.engine import SpawnExecutor
from bulk_http.engine.executor import InProcessExecutor as IPE
from bulk_http.proxies import DomainRateLimiter, ProxyPool


def test_default_executor_builds_proxy_pool(tmp_path: Path) -> None:
    engine = Engine(EngineConfig(workers=1))
    executor = engine._default_executor(tmp_path, None, proxies=["http://p1:1", "http://p2:2"])
    assert isinstance(executor, IPE)
    assert isinstance(executor._proxy_pool, ProxyPool)


def test_default_executor_builds_rate_limiter(tmp_path: Path) -> None:
    engine = Engine(EngineConfig(workers=1, per_domain_rate_limit=5.0))
    executor = engine._default_executor(tmp_path, None, proxies=None)
    assert isinstance(executor, IPE)
    assert isinstance(executor._rate_limiter, DomainRateLimiter)


def test_default_executor_no_proxies_no_rate_limit(tmp_path: Path) -> None:
    engine = Engine(EngineConfig(workers=1))
    executor = engine._default_executor(tmp_path, None, proxies=None)
    assert isinstance(executor, IPE)
    assert executor._proxy_pool is None
    assert executor._rate_limiter is None


def test_default_spawn_executor_receives_proxies(tmp_path: Path) -> None:
    engine = Engine(EngineConfig(workers=4, per_domain_rate_limit=2.0))
    executor = engine._default_executor(tmp_path, None, proxies=["http://p1:1"])
    assert isinstance(executor, SpawnExecutor)
    assert executor._proxies == ["http://p1:1"]
    assert executor._per_domain_rate_limit == 2.0
