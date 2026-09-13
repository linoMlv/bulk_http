"""Read a proxy pool from a text file (one proxy URL per line)."""

from __future__ import annotations

import os


def proxy_pool(path: str | os.PathLike[str], *, encoding: str = "utf-8") -> list[str]:
    """Load a list of proxy URLs from ``path``, ignoring blank lines."""
    with open(path, encoding=encoding) as handle:
        return [line.strip() for line in handle if line.strip()]
