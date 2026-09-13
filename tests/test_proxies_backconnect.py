"""Tests for the backconnect gateway with sticky sessions."""

import itertools
from collections.abc import Callable

from bulk_http.proxies import BackconnectGateway


def _counter() -> Callable[[], str]:
    counter = itertools.count(1)
    return lambda: f"s{next(counter)}"


def test_gateway_without_session_placeholder_returns_url_unchanged() -> None:
    gw = BackconnectGateway("http://user:pass@gateway:8000")
    assert gw.proxy_for() == "http://user:pass@gateway:8000"
    assert gw.proxy_for("example.com") == "http://user:pass@gateway:8000"


def test_gateway_injects_session_id() -> None:
    gw = BackconnectGateway(
        "http://user-session-{session}:pass@gateway:8000", id_generator=_counter()
    )
    assert gw.proxy_for("example.com") == "http://user-session-s1:pass@gateway:8000"


def test_sticky_reuses_same_id_for_same_key() -> None:
    gw = BackconnectGateway("http://u-{session}:p@gw:1", id_generator=_counter())
    first = gw.proxy_for("example.com")
    second = gw.proxy_for("example.com")
    assert first == second == "http://u-s1:p@gw:1"


def test_different_keys_get_different_ids() -> None:
    gw = BackconnectGateway("http://u-{session}:p@gw:1", id_generator=_counter())
    a = gw.proxy_for("a.com")
    b = gw.proxy_for("b.com")
    assert a == "http://u-s1:p@gw:1"
    assert b == "http://u-s2:p@gw:1"


def test_no_key_generates_fresh_id_each_time() -> None:
    gw = BackconnectGateway("http://u-{session}:p@gw:1", id_generator=_counter())
    a = gw.proxy_for()
    b = gw.proxy_for()
    assert a == "http://u-s1:p@gw:1"
    assert b == "http://u-s2:p@gw:1"


def test_default_id_generator_produces_distinct_ids() -> None:
    gw = BackconnectGateway("http://u-{session}:p@gw:1")
    assert gw.proxy_for("a.com") != gw.proxy_for("b.com")
