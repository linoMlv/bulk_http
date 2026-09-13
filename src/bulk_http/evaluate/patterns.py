"""Multi-pattern search over response fragments using Aho-Corasick."""

from __future__ import annotations

import ahocorasick


def _as_text(data: str | bytes) -> str:
    if isinstance(data, str):
        return data
    return data.decode("utf-8", errors="replace")


class PatternMatcher:
    """A compiled multi-pattern matcher.

    The automaton is built once from ``needles`` and reused across many
    fragments. Byte fragments are decoded as UTF-8 with replacement, matching the
    default binary/UTF-8 search semantics. An empty needle set matches nothing;
    callers decide what "no needle constraint" means at the pipeline level.
    """

    __slots__ = ("_automaton", "_empty")

    def __init__(self, needles: tuple[str, ...]) -> None:
        self._empty = len(needles) == 0
        self._automaton = ahocorasick.Automaton()
        if not self._empty:
            for index, needle in enumerate(needles):
                self._automaton.add_word(needle, (index, needle))
            self._automaton.make_automaton()

    @property
    def is_empty(self) -> bool:
        return self._empty

    def search(self, data: str | bytes) -> bool:
        """Return whether any needle occurs in ``data``."""
        if self._empty:
            return False
        text = _as_text(data)
        return any(True for _ in self._automaton.iter(text))

    def find(self, data: str | bytes) -> list[str]:
        """Return every matched needle occurring in ``data``."""
        if self._empty:
            return []
        text = _as_text(data)
        return [value for _, (_, value) in self._automaton.iter(text)]
