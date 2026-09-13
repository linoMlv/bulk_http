"""Process tasks: resolve, proxy, rate-limit, perform, classify and evaluate."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from typing import Protocol
from urllib.parse import urlsplit

from bulk_http.config import EngineConfig, ResolvedRequest
from bulk_http.evaluate import PatternMatcher, Predicate, evaluate
from bulk_http.models import Result, Task
from bulk_http.net.retry import perform_with_retries
from bulk_http.net.transport import Transport
from bulk_http.proxies.health import Outcome, classify_outcome

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]
Jitter = Callable[[], float]


class ProxyProvider(Protocol):
    def select(self, *, now: float) -> str | None: ...
    def report(self, proxy: str, outcome: Outcome, *, now: float) -> None: ...


class RateLimiter(Protocol):
    async def acquire(self, domain: str) -> None: ...


def _domain(url: str) -> str:
    return urlsplit(url).hostname or ""


class TaskProcessor:
    """Turn tasks into results by driving the full per-request pipeline.

    For each task it resolves overrides, picks a proxy (explicit override, else the
    pool), applies the per-domain rate limit, performs the request with retries,
    reports the outcome to the proxy pool, and evaluates the response. Pattern
    matchers are cached per needle set so shared global needles compile once.
    """

    def __init__(
        self,
        config: EngineConfig,
        transport: Transport,
        *,
        predicate: Predicate | None = None,
        concurrency: int | None = None,
        proxy_pool: ProxyProvider | None = None,
        rate_limiter: RateLimiter | None = None,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
        jitter: Jitter = random.random,
    ) -> None:
        self._config = config
        self._transport = transport
        self._predicate = predicate
        self._concurrency = concurrency or config.concurrency_per_worker
        self._proxy_pool = proxy_pool
        self._rate_limiter = rate_limiter
        self._clock = clock
        self._sleep = sleep
        self._jitter = jitter
        self._matchers: dict[tuple[str, ...], PatternMatcher] = {}

    def _matcher_for(self, needles: tuple[str, ...]) -> PatternMatcher:
        matcher = self._matchers.get(needles)
        if matcher is None:
            matcher = PatternMatcher(needles)
            self._matchers[needles] = matcher
        return matcher

    async def process(self, task: Task) -> Result:
        resolved = self._config.effective(task.request)
        resolved, proxy = self._apply_proxy(resolved)
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire(_domain(resolved.url))
        response = await perform_with_retries(
            self._transport, resolved, sleep=self._sleep, jitter=self._jitter
        )
        outcome = classify_outcome(response)
        if proxy is not None and self._proxy_pool is not None:
            self._proxy_pool.report(proxy, outcome, now=self._clock())
        if response.error is not None:
            matched = False
        else:
            matched, _ctx = evaluate(
                status=response.status,
                url=resolved.url,
                headers=response.headers,
                fragment=response.fragment,
                content_encoding=response.content_encoding,
                matcher=self._matcher_for(resolved.needles),
                expected_status=resolved.expected_status,
                predicate=self._predicate,
                meta=resolved.meta,
            )
        return Result(
            source_id=task.source_id,
            url=resolved.url,
            status=response.status,
            matched=matched,
            meta=resolved.meta,
            error=response.error,
            elapsed=response.elapsed,
        )

    def _apply_proxy(self, resolved: ResolvedRequest) -> tuple[ResolvedRequest, str | None]:
        if resolved.proxy is not None:
            return resolved, resolved.proxy
        if self._proxy_pool is None:
            return resolved, None
        proxy = self._proxy_pool.select(now=self._clock())
        if proxy is None:
            return resolved, None
        return replace(resolved, proxy=proxy), proxy

    async def run_batch(self, tasks: Sequence[Task]) -> list[Result]:
        semaphore = asyncio.Semaphore(self._concurrency)

        async def guarded(task: Task) -> Result:
            async with semaphore:
                return await self.process(task)

        return await asyncio.gather(*(guarded(task) for task in tasks))
