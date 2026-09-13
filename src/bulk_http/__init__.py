"""bulk_http: a massive asynchronous, multiprocess HTTP execution engine.

This package streams, sends, filters and persists millions of HTTP requests with
constant memory usage, browser fingerprint impersonation, proxy management and
crash-safe resumption. The public API is progressively assembled across releases.
"""

from bulk_http import sinks, sources
from bulk_http.engine import Engine, RunSummary
from bulk_http.models import Request, Result

__version__ = "0.1.0"

__all__ = [
    "Engine",
    "Request",
    "Result",
    "RunSummary",
    "__version__",
    "sinks",
    "sources",
]
