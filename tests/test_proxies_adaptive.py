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


async def test_ban_after_consecutive_failures_at_min_rate() -> None:
    lim = _limiter(start_rate=1.0, min_rate=1.0, ban_failures=5)  # always at min
    with pytest.raises(BanSuspectedError):
        for _ in range(5):
            lim.record("a.com", "rate_limited")


async def test_descent_failures_do_not_trigger_ban() -> None:
    # Failures while the rate is still above the minimum must not count for the ban.
    lim = _limiter(start_rate=8.0, min_rate=1.0, decrease_factor=0.5, ban_failures=3)
    # 8 -> 4 -> 2 -> 1 : three failures during descent, still above/at boundary.
    lim.record("a.com", "rate_limited")  # was 8 (>min) -> 4
    lim.record("a.com", "rate_limited")  # was 4 (>min) -> 2
    lim.record("a.com", "rate_limited")  # was 2 (>min) -> 1 (min reached now)
    assert lim.rate("a.com") == pytest.approx(1.0)  # no ban yet
    # now three more failures *at* the minimum -> ban
    with pytest.raises(BanSuspectedError):
        for _ in range(3):
            lim.record("a.com", "rate_limited")


async def test_no_ban_when_failures_below_threshold() -> None:
    lim = _limiter(start_rate=1.0, min_rate=1.0, ban_failures=8)
    for _ in range(5):
        lim.record("a.com", "rate_limited")  # 5 < 8, at min but not enough
    assert lim.rate("a.com") == pytest.approx(1.0)


async def test_success_at_min_resets_failure_streak() -> None:
    lim = _limiter(start_rate=1.0, min_rate=1.0, ban_failures=3, increase_after=100)
    lim.record("a.com", "rate_limited")
    lim.record("a.com", "rate_limited")
    lim.record("a.com", "ok")  # resets the at-min failure streak
    lim.record("a.com", "rate_limited")
    lim.record("a.com", "rate_limited")  # only 2 consecutive at-min failures -> no ban
    assert lim.rate("a.com") == pytest.approx(1.0)


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
        {"max_attempts": 0},  # must be >= 1
        {"ban_failures": 0},  # must be >= 1
    ],
)
def test_adaptive_config_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        AdaptiveRateConfig(**kwargs)  # type: ignore[arg-type]
