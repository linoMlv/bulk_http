"""Tests for worker sizing and event-loop selection logic."""

from bulk_http.concurrency import (
    choose_loop,
    compute_workers,
    effective_concurrency,
    resolve_workers,
)


def test_effective_concurrency_capped_on_windows() -> None:
    assert effective_concurrency(2000, os_name="windows") == 450
    assert effective_concurrency(300, os_name="windows") == 300


def test_effective_concurrency_uncapped_on_linux() -> None:
    assert effective_concurrency(2000, os_name="linux") == 2000


def test_compute_workers_windows_scales_horizontally() -> None:
    # Target 4000 in flight, ~450 per worker -> ceil(4000/450) = 9
    assert compute_workers(4000, 450, os_name="windows") == 9


def test_compute_workers_linux() -> None:
    assert compute_workers(4000, 2000, os_name="linux") == 2


def test_compute_workers_at_least_one() -> None:
    assert compute_workers(1, 450, os_name="windows") == 1
    assert compute_workers(0, 450, os_name="linux") == 1


def test_compute_workers_respects_windows_cap_even_with_large_per_worker() -> None:
    # per_worker 2000 requested but capped to 450 on windows
    assert compute_workers(4000, 2000, os_name="windows") == 9


def test_resolve_workers_explicit_int() -> None:
    assert resolve_workers(6, os_name="linux", cpu_count=4) == 6


def test_resolve_workers_auto_uses_cpu_count() -> None:
    assert resolve_workers("auto", os_name="linux", cpu_count=8) == 8


def test_resolve_workers_auto_floor_one() -> None:
    assert resolve_workers("auto", os_name="linux", cpu_count=None) == 1


def test_choose_loop() -> None:
    assert choose_loop("windows", uvloop_available=True) == "selector"
    assert choose_loop("linux", uvloop_available=True) == "uvloop"
    assert choose_loop("linux", uvloop_available=False) == "default"
    assert choose_loop("darwin", uvloop_available=True) == "uvloop"


def test_run_executes_coroutine_on_os_loop() -> None:
    from bulk_http.concurrency import run

    async def work() -> int:
        return 42

    assert run(work()) == 42
