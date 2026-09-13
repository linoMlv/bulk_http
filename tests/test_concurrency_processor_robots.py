"""The processor honours a robots gate: skip disallowed, throttle allowed."""

from bulk_http.concurrency import TaskProcessor
from bulk_http.concurrency.processor import RobotsGate
from bulk_http.config import EngineConfig
from bulk_http.models import Request, Task
from bulk_http.net import FakeTransport, RawResponse


async def _noop_sleep(delay: float) -> None:
    return None


class FakeRobots:
    def __init__(self, *, allow: bool) -> None:
        self._allow = allow
        self.throttled: list[str] = []

    async def allowed(self, url: str) -> bool:
        return self._allow

    async def throttle(self, url: str) -> None:
        self.throttled.append(url)


def _proc(transport: FakeTransport, robots: RobotsGate) -> TaskProcessor:
    return TaskProcessor(
        EngineConfig(), transport, robots=robots, sleep=_noop_sleep, jitter=lambda: 0.0
    )


async def test_disallowed_url_is_skipped_without_request() -> None:
    transport = FakeTransport.constant(RawResponse(status=200, url="u", fragment=b"ok"))
    proc = _proc(transport, FakeRobots(allow=False))
    result = await proc.process(Task(source_id=0, request=Request(url="https://a.com/admin")))
    assert result.matched is False
    assert result.error == "robots_disallowed"
    assert result.status is None
    assert transport.calls == []  # no network request was made


async def test_allowed_url_is_throttled_then_requested() -> None:
    transport = FakeTransport.constant(RawResponse(status=200, url="u", fragment=b"ok"))
    robots = FakeRobots(allow=True)
    proc = _proc(transport, robots)
    result = await proc.process(Task(source_id=0, request=Request(url="https://a.com/page")))
    assert result.status == 200
    assert robots.throttled == ["https://a.com/page"]
    assert len(transport.calls) == 1
