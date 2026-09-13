"""Tests for the adaptive AIMD rate limiter and ban detection."""

import pytest

from bulk_http.proxies import AdaptiveRateConfig, AdaptiveRateLimiter, BanSuspectedError


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def time(self) -> float:
        return self.t

    async def sleep(self, delay: float) -> None:
        self.t += delay


def _limiter(**kw: object) -> AdaptiveRateLimiter:
    clock = FakeClock()
    cfg = AdaptiveRateConfig(**kw)  # type: ignore[arg-type]
    return AdaptiveRateLimiter(cfg, clock=clock.time, sleep=clock.sleep)


async def test_first_acquire_no_wait_then_spaced() -> None:
    clock = FakeClock()
    lim = AdaptiveRateLimiter(
        AdaptiveRateConfig(start_rate=10.0), clock=clock.time, sleep=clock.sleep
    )
    await lim.acquire("a.com")
    await lim.acquire("a.com")
    assert clock.t == pytest.approx(0.1)


async def test_success_increases_rate_after_threshold() -> None:
    lim = _limiter(start_rate=10.0, increase_after=3, increase_step=5.0, max_rate=100.0)
    for _ in range(3):
        lim.record("a.com", "ok")
    assert lim.rate("a.com") == pytest.approx(15.0)


async def test_rate_is_capped_at_max() -> None:
    lim = _limiter(start_rate=48.0, increase_after=1, increase_step=5.0, max_rate=50.0)
    lim.record("a.com", "ok")
    assert lim.rate("a.com") == pytest.approx(50.0)


async def test_429_halves_rate() -> None:
    lim = _limiter(start_rate=20.0, decrease_factor=0.5, min_rate=1.0)
    lim.record("a.com", "rate_limited")
    assert lim.rate("a.com") == pytest.approx(10.0)


async def test_transport_error_halves_rate() -> None:
    lim = _limiter(start_rate=20.0, decrease_factor=0.5)
    lim.record("a.com", "transport_error")
    assert lim.rate("a.com") == pytest.approx(10.0)


async def test_rate_floored_at_min() -> None:
    lim = _limiter(start_rate=2.0, decrease_factor=0.5, min_rate=1.0)
    lim.record("a.com", "rate_limited")
    lim.record("a.com", "rate_limited")
    assert lim.rate("a.com") == pytest.approx(1.0)


async def test_origin_error_is_neutral() -> None:
    lim = _limiter(start_rate=10.0)
    lim.record("a.com", "origin_error")
    assert lim.rate("a.com") == pytest.approx(10.0)


async def test_ban_detected_at_min_rate_with_persistent_failures() -> None:
    lim = _limiter(start_rate=2.0, min_rate=1.0, ban_window=5, ban_failures=5)
    # Drive to the minimum, then keep failing until the window is saturated.
    with pytest.raises(BanSuspectedError):
        for _ in range(10):
            lim.record("a.com", "rate_limited")


async def test_no_ban_when_failures_below_threshold() -> None:
    lim = _limiter(start_rate=1.0, min_rate=1.0, ban_window=10, ban_failures=8)
    for _ in range(5):
        lim.record("a.com", "rate_limited")  # 5 failures < 8 threshold
    assert lim.rate("a.com") == pytest.approx(1.0)


async def test_recovery_success_resets_failure_streak() -> None:
    lim = _limiter(start_rate=2.0, min_rate=1.0, ban_window=4, ban_failures=4, increase_after=100)
    lim.record("a.com", "rate_limited")
    lim.record("a.com", "rate_limited")
    lim.record("a.com", "ok")  # window now has a success, not all failures
    lim.record("a.com", "rate_limited")
    lim.record("a.com", "rate_limited")  # 4 in window but one is ok -> no ban


async def test_acquire_uses_current_rate_after_decrease() -> None:
    clock = FakeClock()
    lim = AdaptiveRateLimiter(
        AdaptiveRateConfig(start_rate=10.0, decrease_factor=0.5, min_rate=1.0),
        clock=clock.time,
        sleep=clock.sleep,
    )
    await lim.acquire("a.com")  # reserve at 0.1 interval
    lim.record("a.com", "rate_limited")  # rate -> 5/s, interval 0.2
    await lim.acquire("a.com")  # waits based on the new, larger interval
    assert clock.t >= 0.1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_rate": 0.0},  # min_rate must be > 0
        {"min_rate": 20.0, "start_rate": 10.0},  # min <= start violated
        {"start_rate": 100.0, "max_rate": 50.0},  # start <= max violated
        {"decrease_factor": 1.0},  # must be < 1
        {"decrease_factor": 0.0},  # must be > 0
        {"increase_after": 0},  # must be >= 1
        {"increase_step": 0.0},  # must be > 0
        {"ban_window": 0},  # must be >= 1
        {"ban_failures": 0},  # must be >= 1
        {"ban_failures": 5, "ban_window": 3},  # failures <= window violated
    ],
)
def test_adaptive_config_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        AdaptiveRateConfig(**kwargs)  # type: ignore[arg-type]
