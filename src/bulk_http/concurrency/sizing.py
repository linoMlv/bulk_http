"""Worker sizing and OS-appropriate event-loop selection.

Windows' SelectorEventLoop is capped at 512 sockets, so per-worker concurrency is
limited to ~450 and the target is reached by scaling out processes. Linux uses
uvloop with no such cap. The decision functions take the OS name explicitly so
they can be tested deterministically on any platform.
"""

from __future__ import annotations

import asyncio
import math
import platform
import sys
from collections.abc import Coroutine
from typing import Any, Literal, TypeVar

_WINDOWS_SOCKET_CAP = 450

_T = TypeVar("_T")


def effective_concurrency(per_worker_cap: int, *, os_name: str) -> int:
    """Cap per-worker concurrency to what the OS event loop can sustain."""
    if os_name == "windows":
        return min(per_worker_cap, _WINDOWS_SOCKET_CAP)
    return per_worker_cap


def compute_workers(concurrency_target: int, per_worker_cap: int, *, os_name: str) -> int:
    """Number of workers needed to reach ``concurrency_target`` in flight."""
    cap = effective_concurrency(per_worker_cap, os_name=os_name)
    return max(1, math.ceil(concurrency_target / cap))


def resolve_workers(workers: int | Literal["auto"], *, os_name: str, cpu_count: int | None) -> int:
    """Resolve the configured worker count, expanding ``"auto"`` to the CPU count."""
    if workers == "auto":
        return max(1, cpu_count or 1)
    return workers


def choose_loop(
    os_name: str,
    *,
    uvloop_available: bool,
    winloop_available: bool = False,
    prefer_winloop: bool = False,
) -> str:
    """Pick the event-loop implementation for ``os_name``.

    Windows must use the SelectorEventLoop by default (the ProactorEventLoop
    cannot drive libcurl's external descriptors); POSIX prefers uvloop when
    available. ``winloop`` is an opt-in Windows accelerator that must be validated
    on Windows before use — it is only chosen when both available and explicitly
    preferred, and the reliable Selector path stays the default. (A ``curl_multi_poll``
    thread is another possible high-concurrency Windows accelerator, left
    unintegrated pending a Windows spike.)
    """
    if os_name == "windows":
        if winloop_available and prefer_winloop:
            return "winloop"
        return "selector"
    if uvloop_available:
        return "uvloop"
    return "default"


def _current_os() -> str:
    return "windows" if sys.platform.startswith("win") else platform.system().lower()


def run(coro: Coroutine[Any, Any, _T], *, os_name: str | None = None) -> _T:
    """Run ``coro`` on the OS-appropriate event loop and return its result.

    On Windows the SelectorEventLoop policy is installed before running; on POSIX
    uvloop is used when available (via ``uvloop.run``, the supported entry point
    on Python 3.12+), otherwise the default loop. Intended as the per-worker
    entry point.
    """
    resolved_os = os_name or _current_os()
    if resolved_os == "windows":  # pragma: no cover - Windows only
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
        return asyncio.run(coro)
    try:
        import uvloop
    except ImportError:  # pragma: no cover - uvloop is a POSIX dependency
        return asyncio.run(coro)
    return uvloop.run(coro)
