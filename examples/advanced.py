"""Advanced example: CSV input, a typed predicate, a proxy pool and resumable output.

Input `targets.csv` maps columns to request fields; each row is tested against a
predicate over the parsed response, requests go through a rotating proxy pool, and
the campaign can be interrupted and resumed via its checkpoint file.

    python examples/advanced.py
"""

from __future__ import annotations

from bulk_http import Engine, sources
from bulk_http.models import EvalContext


def has_login_form(ctx: EvalContext) -> bool:
    """Keep HTML pages that expose a password field."""
    if ctx.type != "html" or ctx.dom is None:
        return False
    return ctx.dom.css_first("input[type=password]") is not None


def main() -> None:
    engine = Engine(
        workers=4,
        chunk_size=1000,
        impersonate="chrome",
        stream_cut=50_000,
        follow_redirects=True,
        per_domain_rate_limit=5.0,
        identity_header=("X-Contact", "security@example.com"),
        authorization="bug-bounty ACME scope #123",
        checkpoint="campaign.ckpt",
    )
    summary = engine.run(
        source=sources.csv("targets.csv", mapping={"url": 0, "needle": 1, "keep": [2, 3]}),
        predicate=has_login_form,
        proxies=sources.proxy_pool("proxies.txt"),
        out_dir="out",
    )
    print(summary)


if __name__ == "__main__":
    main()
