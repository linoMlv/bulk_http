"""The spawn worker builds a proxy pool and applies it to requests."""

from pathlib import Path

from bulk_http.config import EngineConfig, ResolvedRequest
from bulk_http.models import Request, Task
from bulk_http.net import FakeTransport, RawResponse


def test_spawn_worker_uses_proxy_from_pool(tmp_path: Path) -> None:
    from bulk_http.engine import spawn as spawn_mod

    captured: list[str | None] = []

    def factory() -> FakeTransport:
        def responder(resolved: ResolvedRequest, attempt: int) -> RawResponse:
            captured.append(resolved.proxy)
            return RawResponse(status=200, url=resolved.url, fragment=b"ok")

        return FakeTransport(responder)

    spawn_mod._SPAWN_STATE.clear()
    spawn_mod._SPAWN_STATE.update(
        config=EngineConfig(),
        predicate=None,
        factory=factory,
        out_dir=str(tmp_path),
        os_name="linux",
        proxies=["http://pool-proxy:9"],
        per_domain_rate_limit=None,
    )
    spawn_mod._spawn_run_batch((0, [Task(source_id=0, request=Request(url="https://a.com"))]))
    assert captured == ["http://pool-proxy:9"]
    spawn_mod._SPAWN_STATE.clear()
