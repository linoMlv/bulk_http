"""A backconnect (rotating gateway) proxy with optional sticky sessions."""

from __future__ import annotations

import uuid
from collections.abc import Callable

_SESSION_PLACEHOLDER = "{session}"


def _default_id() -> str:
    return uuid.uuid4().hex[:12]


class BackconnectGateway:
    """A single rotating gateway that can pin an upstream IP via a session id.

    ``url_template`` may contain a ``{session}`` placeholder (typically inside the
    username, e.g. ``http://user-session-{session}:pass@gateway:port``). When it
    does, :meth:`proxy_for` fills it with a session id: reused for a given sticky
    ``key`` (so the same upstream IP is kept), or freshly generated when no key is
    given. Without the placeholder, the URL is returned unchanged (pure rotation).
    """

    def __init__(
        self,
        url_template: str,
        *,
        id_generator: Callable[[], str] = _default_id,
    ) -> None:
        self._template = url_template
        self._id_generator = id_generator
        self._sticky: dict[str, str] = {}

    def proxy_for(self, key: str | None = None) -> str:
        if _SESSION_PLACEHOLDER not in self._template:
            return self._template
        if key is None:
            session_id = self._id_generator()
        else:
            session_id = self._sticky.get(key) or self._id_generator()
            self._sticky[key] = session_id
        return self._template.replace(_SESSION_PLACEHOLDER, session_id)
