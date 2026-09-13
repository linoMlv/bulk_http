"""A deterministic in-memory transport for testing the layers above the network."""

from __future__ import annotations

from collections.abc import Callable

from bulk_http.config import ResolvedRequest
from bulk_http.net.transport import RawResponse

Responder = Callable[[ResolvedRequest, int], RawResponse]


class FakeTransport:
    """A transport driven by a responder callback, recording every call.

    The responder receives the resolved request and a zero-based attempt counter
    (how many times this transport has already been called), enabling tests of
    retry behavior without any real networking.
    """

    def __init__(self, responder: Responder) -> None:
        self._responder = responder
        self.calls: list[ResolvedRequest] = []

    @classmethod
    def constant(cls, response: RawResponse) -> FakeTransport:
        return cls(lambda resolved, attempt: response)

    @classmethod
    def sequence(cls, responses: list[RawResponse]) -> FakeTransport:
        def responder(resolved: ResolvedRequest, attempt: int) -> RawResponse:
            index = min(attempt, len(responses) - 1)
            return responses[index]

        return cls(responder)

    async def perform(self, resolved: ResolvedRequest) -> RawResponse:
        attempt = len(self.calls)
        self.calls.append(resolved)
        return self._responder(resolved, attempt)
