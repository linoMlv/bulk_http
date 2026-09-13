"""Tests for the transport protocol and the fake transport."""

from bulk_http.config import EngineConfig, ResolvedRequest
from bulk_http.models import Request
from bulk_http.net import FakeTransport, RawResponse, Transport

CFG = EngineConfig()


def _resolved(url: str = "https://a.com") -> ResolvedRequest:
    return CFG.effective(Request(url=url))


def test_raw_response_defaults() -> None:
    r = RawResponse(status=200, url="https://a.com")
    assert r.status == 200
    assert r.headers == {}
    assert r.fragment == b""
    assert r.truncated is False
    assert r.error is None


async def test_fake_transport_constant_returns_same_response() -> None:
    resp = RawResponse(status=200, url="https://a.com", fragment=b"body")
    transport: Transport = FakeTransport.constant(resp)
    out = await transport.perform(_resolved())
    assert out is resp


async def test_fake_transport_records_calls() -> None:
    transport = FakeTransport.constant(RawResponse(status=200, url="u"))
    await transport.perform(_resolved("https://a.com"))
    await transport.perform(_resolved("https://b.com"))
    assert [r.url for r in transport.calls] == ["https://a.com", "https://b.com"]


async def test_fake_transport_sequence_cycles_through_responses() -> None:
    responses = [
        RawResponse(status=None, url="u", error="timeout"),
        RawResponse(status=200, url="u", fragment=b"ok"),
    ]
    transport = FakeTransport.sequence(responses)
    first = await transport.perform(_resolved())
    second = await transport.perform(_resolved())
    assert first.error == "timeout"
    assert second.status == 200


async def test_fake_transport_responder_sees_attempt_number() -> None:
    def responder(resolved: ResolvedRequest, attempt: int) -> RawResponse:
        if attempt == 0:
            return RawResponse(status=None, url=resolved.url, error="reset")
        return RawResponse(status=200, url=resolved.url)

    transport = FakeTransport(responder)
    r0 = await transport.perform(_resolved())
    r1 = await transport.perform(_resolved())
    assert r0.error == "reset"
    assert r1.status == 200
