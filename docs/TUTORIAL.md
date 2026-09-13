# bulk_http tutorial

A hands-on guide to running large HTTP campaigns with `bulk_http`: sending and
filtering many requests, keeping memory flat, staying polite, and resuming safely
after a crash.

- [1. What it is and when to use it](#1-what-it-is-and-when-to-use-it)
- [2. Installation](#2-installation)
- [3. Core concepts](#3-core-concepts)
- [4. Your first campaign](#4-your-first-campaign)
- [5. Input sources](#5-input-sources)
- [6. Filtering responses](#6-filtering-responses)
- [7. Reading less: Fast-Status and Stream-Cut](#7-reading-less-fast-status-and-stream-cut)
- [8. Concurrency and scaling](#8-concurrency-and-scaling)
- [9. Proxies](#9-proxies)
- [10. Rate limiting](#10-rate-limiting)
- [11. Timeouts and retries](#11-timeouts-and-retries)
- [12. Output and crash-safe resume](#12-output-and-crash-safe-resume)
- [13. Metrics](#13-metrics)
- [14. Responsible use](#14-responsible-use)
- [15. HTTP/3](#15-http3)
- [16. A complete worked example](#16-a-complete-worked-example)
- [17. Troubleshooting](#17-troubleshooting)
- [18. API cheat sheet](#18-api-cheat-sheet)

---

## 1. What it is and when to use it

`bulk_http` is an execution engine for sending, analysing and conditionally
filtering large numbers of HTTP requests (millions) with a memory footprint that
stays constant regardless of input size. Reach for it when you need to:

- check a very large list of URLs (status, redirects, presence of a string),
- pre-qualify targets before a heavier crawl,
- audit assets at scale within an authorised scope.

It is **not** a browser: it fetches raw HTTP responses. Content rendered by
client-side JavaScript (single-page apps) is not visible to it — filter on what
the server actually returns.

## 2. Installation

```bash
pip install bulk_http          # or: uv add bulk_http
```

Requires Python 3.11+. On Linux/macOS, `uvloop` is used automatically when
available for extra throughput.

## 3. Core concepts

| Concept | What it is |
| --- | --- |
| `Engine` | The coordinator. Holds global defaults and runs a campaign. |
| `EngineConfig` | The typed set of global defaults (concurrency, timeouts, proxies…). |
| `Request` | One request's data and per-request overrides (url, method, headers, needle…). |
| **source** | A lazy stream of tasks (`sources.text`, `sources.csv`, …). |
| **predicate** | A function deciding whether a response is a match. |
| **out_dir** | Where per-worker NDJSON output is written. |
| **checkpoint** | A file enabling crash-safe resume. |

The mental model: a **source** streams tasks → the engine sends them across
**workers** with bounded **concurrency** → each response is **evaluated** (status,
keyword, predicate) → matches are written to **NDJSON**, one file per worker →
progress is committed to a **checkpoint** so a re-run resumes exactly once.

> **Spawn guard.** Workers use the `spawn` start method, so a script that runs an
> engine must guard its entry point:
>
> ```python
> if __name__ == "__main__":
>     main()
> ```

## 4. Your first campaign

`targets.txt` — one URL per line. Keep the pages that contain the word `admin`:

```python
from bulk_http import Engine, sources


def main() -> None:
    engine = Engine(impersonate="chrome")
    summary = engine.run(
        sources.text("targets.txt"),
        needle="admin",
        out_dir="out",
    )
    print(summary)  # chunks, matched, skipped, metrics


if __name__ == "__main__":
    main()
```

Matches land in `out/worker-*.ndjson`, one JSON object per line:

```json
{"source_id": 0, "url": "https://a.com", "status": 200, "matched": true, "data": {}, "meta": {}, "error": null, "elapsed": 0.12}
```

## 5. Input sources

Every source streams lazily; the whole input is never loaded at once.

```python
from bulk_http import sources
from bulk_http.models import Request

sources.memory(["https://a.com", "https://b.com"])  # URLs…
sources.memory([Request(url="https://a.com", method="POST", body=b"x")])  # …or Request objects
sources.text("urls.txt")  # one URL per line
sources.csv("t.csv", mapping={"url": 0, "needle": 1, "keep": [2, 3]})
sources.tsv("t.tsv", mapping={"url": 0})
sources.json("t.jsonl")  # one JSON object per line
```

**CSV/TSV mapping** links request attributes to zero-based column indices. The
special key `"keep"` preserves extra columns as metadata, reinjected into the
output (`meta`). Recognised keys include `url`, `method`, `headers`, `cookies`,
`body`, `needle`/`needles`, `expected_status`, `proxy`, `stream_cut`, and more.

**JSON Lines** maps object keys to the same attributes; unknown keys become
metadata:

```jsonl
{"url": "https://a.com", "needle": "admin", "campaign": "q3"}
```

**Per-request overrides.** Any engine default can be overridden per row via a
`Request`:

```python
Request(
    url="https://a.com",
    method="POST",
    headers={"X-Api-Key": "…"},
    body=b'{"q":1}',
    stream_cut=4096,
    expected_status=frozenset({200, 201}),
)
```

## 6. Filtering responses

Conditions combine with **AND** — a response is kept only if every configured
check passes. With no condition, everything matches.

**By status:**

```python
Request(url="https://a.com", expected_status=200)
Request(url="https://a.com", expected_status=frozenset({200, 301, 302}))
```

**By keyword** (Aho-Corasick over the decompressed body):

```python
engine.run(source, needle="Access denied")  # global, applies to all
Request(url="https://a.com", needles=("admin", "root"))  # per-URL
```

**By predicate** — a callable over a typed context:

```python
from bulk_http.models import EvalContext


def is_admin_json(ctx: EvalContext) -> bool:
    return ctx.type == "json" and bool(ctx.data) and ctx.data.get("admin") is True


engine.run(source, predicate=is_admin_json)
```

The context exposes:

| Field | Meaning |
| --- | --- |
| `ctx.type` | `"json"`, `"html"` or `"text"` (from `Content-Type`) |
| `ctx.data` | parsed JSON (when `type == "json"`, else `None`) |
| `ctx.dom` | a selectolax HTML tree (when `type == "html"`) |
| `ctx.text` | decoded text (when `type == "text"`) |
| `ctx.raw` | the received (decompressed) bytes |
| `ctx.status`, `ctx.headers`, `ctx.url`, `ctx.meta` | response metadata |

HTML example:

```python
def has_login_form(ctx):
    return (
        ctx.type == "html"
        and ctx.dom is not None
        and ctx.dom.css_first("input[type=password]") is not None
    )
```

> The predicate runs in worker processes under `spawn`, so it is serialized with
> cloudpickle — lambdas and closures work, but anything they capture must itself
> be picklable (no open sockets, file handles or DB connections).

## 7. Reading less: Fast-Status and Stream-Cut

Two ways to avoid downloading full bodies:

```python
Engine(fast_status=True)  # abort right after headers (status only)
Engine(stream_cut=15_000)  # abort once 15 KB have been received
Engine(stream_cut=15_000, cut_on="decoded")  # 15 KB of *decompressed* content
```

- `cut_on="wire"` (default) counts bytes as received (compressed) — it minimises
  bandwidth/proxy cost. A truncated compressed fragment is still decompressed
  tolerantly before searching.
- `cut_on="decoded"` counts decompressed bytes — deterministic "amount of
  content", slightly less network-efficient.

Use Stream-Cut when your signal (a `<title>`, a header, an error banner) lives
near the start of the page.

## 8. Concurrency and scaling

```python
Engine(
    workers="auto",  # "auto" = CPU count; or an integer
    concurrency_per_worker=450,  # sockets in flight per worker
    chunk_size=1000,  # tasks dispatched per batch (500–2000)
    in_flight_batches=4,  # bounded backpressure
    max_tasks_per_child=50_000,  # recycle workers to bound leaks
)
```

- **Total in-flight ≈ workers × concurrency_per_worker.** Aim for
  `throughput × average_latency`. For 2000 req/s at 2 s latency that's ~4000 in
  flight.
- **Windows** caps sockets per process (~450); reach the target by scaling out
  processes rather than raising per-worker concurrency. The engine sizes this for
  you.
- `workers=1` runs in-process (no spawn overhead) — great for small jobs or a
  single throttling host; use more workers to spread CPU across cores.

## 9. Proxies

At scale, a single IP gets banned or rate-limited fast (see §10). Provide a pool:

```python
from bulk_http import Engine, sources

engine.run(source, proxies=sources.proxy_pool("proxies.txt"))  # one proxy URL per line
```

The pool round-robins over **healthy** proxies. A per-proxy circuit breaker
quarantines a proxy on a sustained transport-failure rate and backs off on 429,
while origin statuses (403/5xx) are blamed on the target, not the proxy.

Other options:

```python
Request(url="https://a.com", proxy="http://user:pass@host:port")  # fixed, per request

from bulk_http.proxies import BackconnectGateway

gw = BackconnectGateway("http://user-session-{session}:pass@gw:8000")
gw.proxy_for("example.com")  # sticky: same upstream IP per key
```

## 10. Rate limiting

**Syntax** — requests per second, per domain:

```python
Engine(per_domain_rate_limit=8.0)
```

**Picking a value.** The right number depends on the target and is found
empirically. A practical recipe:

1. Run a small sample at a candidate rate.
2. Inspect `summary.metrics.by_status` — if you see `429`, the rate is too high.
3. Step down until 429s disappear; that's your sustainable rate.

```python
summary = engine.run(sample_source, out_dir="out")
print(summary.metrics.by_status)  # e.g. {200: 118, 429: 2}  -> lower the rate
```

**Why 429 storms happen.** Without a rate limit, high concurrency on a single
host will burst; many servers answer `429 Too Many Requests`. Either lower
`per_domain_rate_limit`, or spread the load across a **proxy pool** (§9) — from a
single IP the ceiling is the server's, not the engine's.

> Retries treat `429` as a signal to back off (not to quarantine the proxy), so a
> few transient 429s are retried automatically; a *sustained* 429 rate means the
> rate is genuinely too high.

### Adaptive rate limiting (optional)

Instead of guessing a fixed value, let the engine find a sustainable rate on its
own. It is **opt-in** via `adaptive_rate=` and off by default. The algorithm is
AIMD (like TCP), per domain: the rate nudges **up** after a run of clean
responses and is **halved** on a 429 or transport error, staying within
`[min_rate, max_rate]`. Origin statuses (403/5xx) are treated as the target's
problem and left neutral.

```python
from bulk_http import Engine, AdaptiveRateConfig

engine = Engine(
    adaptive_rate=AdaptiveRateConfig(
        start_rate=10.0,  # req/s per domain to begin with
        min_rate=1.0,
        max_rate=50.0,
        increase_step=1.0,  # +1 req/s ...
        increase_after=20,  # ... after 20 clean responses in a row
        decrease_factor=0.5,  # halve on a 429 / transport error
        ban_window=30,  # sliding window of recent outcomes
        ban_failures=20,  # failures within it, *while at min_rate*, => ban
    ),
)
```

**Ban detection / stop.** If the rate has already fallen to `min_rate` and
failures still dominate the window, a real IP ban is likely — continuing would be
pointless (or harmful). The engine raises `BanSuspectedError`, which stops the
campaign. Because output is checkpointed, you can fix the situation (rotate IPs,
wait) and resume:

```python
from bulk_http import Engine, AdaptiveRateConfig, BanSuspectedError, sources

engine = Engine(adaptive_rate=AdaptiveRateConfig(), checkpoint="campaign.ckpt")
try:
    summary = engine.run(sources.text("urls.txt"), out_dir="out")
except BanSuspectedError:
    print("stopped: target is banning us — rotate proxies, then re-run to resume")
```

Adaptive rate combines with retries (§11): a 429 is both retried with backoff and
used to lower the rate, so the campaign self-tunes toward zero sustained failures.
Under `spawn`, each worker adapts its own rate independently.

## 11. Timeouts and retries

```python
Engine(
    timeout=30.0,  # per attempt (connect + read)
    total_timeout=60.0,  # whole-URL budget, retries + backoffs included
    retries=2,  # extra attempts for retryable failures
    retry_non_idempotent=False,  # POST/PUT/PATCH/DELETE not retried by default
)
```

Retries are **method-aware**: GET/HEAD/OPTIONS are replayed on transport errors
and 429; non-idempotent methods are not, unless you opt in. Backoff is
exponential with jitter; `total_timeout` stops starting new attempts once the
per-URL deadline would be crossed.

## 12. Output and crash-safe resume

Each worker appends to its own NDJSON file under `out_dir`. Output is durable:
a batch is committed to the checkpoint manifest only **after** its NDJSON is
flushed and `fsync`ed.

```python
engine = Engine(checkpoint="campaign.ckpt")
engine.run(source, out_dir="out")  # interrupt any time (Ctrl-C, crash, power loss)
engine.run(source, out_dir="out")  # re-run: resumes, each row processed once
```

On resume, partial writes past the last commit are truncated away and only the
pending/undistributed batches are replayed — exactly-once at the batch grain.

Convert to CSV at the end:

```python
from pathlib import Path
from bulk_http.sinks import export_csv

export_csv(list(Path("out").glob("*.ndjson")), "results.csv")
# columns default to the base fields + every metadata key seen
```

## 13. Metrics

`run` returns a `RunSummary`; `summary.metrics` aggregates the whole campaign:

```python
summary = engine.run(source, out_dir="out")
m = summary.metrics
print(m.total, m.matched, m.by_status, m.errors)
print(f"p50/p95/p99 = {m.p50:.3f}/{m.p95:.3f}/{m.p99:.3f}s, {m.throughput:.0f} req/s")
```

Or receive it via a callback:

```python
engine.run(source, metrics_callback=lambda m: print(m.as_dict()))
```

Counts and status/error distributions are exact; latency percentiles use bounded
reservoir sampling, so memory stays flat.

## 14. Responsible use

Use `bulk_http` within an authorised scope. The engine gives you the means to be
polite and contactable:

```python
Engine(
    respect_robots=True,  # off by default
    per_domain_rate_limit=5.0,
    allowlist=("example.com",),
    denylist=("do-not-touch.com",),
    identity_header=("X-Contact", "security@example.com"),
    authorization="bug-bounty ACME scope #123",  # attached to every output row
)
```

With `respect_robots=True`, disallowed URLs are skipped (a `robots_disallowed`
result) and per-host crawl-delay is honoured. Legal responsibility for use rests
with you.

## 15. HTTP/3

HTTP/3 is opt-in per request and requires a QUIC-capable libcurl build (detected
at runtime) plus a UDP-capable proxy for proxied traffic:

```python
Request(url="https://a.com", http_version="h3")
```

If h3 is requested on a build without QUIC, the request returns an
`http3_unavailable` error rather than failing obscurely. The default (`"auto"`)
negotiates HTTP/2 or HTTP/1.1.

## 16. A complete worked example

Split a CSV of URLs into two files by whether each page shows an error banner,
politely and resumably:

```python
import csv
from pathlib import Path

import orjson
from bulk_http import Engine, Request, sources


def main() -> None:
    with open("targets.csv", newline="") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0]) if rows else ["URL"]

    engine = Engine(
        workers=1,
        concurrency_per_worker=32,
        per_domain_rate_limit=8.0,  # tune per §10
        stream_cut=16_384,
        retries=6,
        checkpoint="split.ckpt",
    )
    # keep the original URL in meta so we can map results back to CSV rows
    reqs = [Request(url=r["URL"], meta={"src": r["URL"]}) for r in rows]
    out = "out"
    summary = engine.run(sources.memory(reqs), needle="Something went wrong", out_dir=out)

    matched = {
        orjson.loads(line)["meta"]["src"]
        for p in Path(out).glob("*.ndjson")
        for line in p.read_bytes().splitlines()
        if line.strip()
    }
    with open("errors.csv", "w", newline="") as fe, open("ok.csv", "w", newline="") as fk:
        we, wk = csv.DictWriter(fe, fieldnames), csv.DictWriter(fk, fieldnames)
        we.writeheader()
        wk.writeheader()
        for r in rows:
            (we if r["URL"] in matched else wk).writerow(r)

    print(summary.metrics.by_status, "->", len(matched), "errors")


if __name__ == "__main__":
    main()
```

## 17. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| Lots of `429` in `by_status` | Rate too high for one IP. Lower `per_domain_rate_limit`, or add a proxy pool (§9). |
| `RuntimeError` about `spawn` / freeze | Missing `if __name__ == "__main__":` guard around the run. |
| Predicate raises `PicklingError` | The predicate captured something unpicklable. Keep closures pure, or pass an import path. |
| Filtering finds nothing on a JS site | The site is a SPA; the text is rendered client-side. Filter on what the server returns (an API endpoint, an error page). |
| Memory grows with input | You materialised the input (e.g. `list(...)`). Use a lazy source/generator. |
| Compressed body, needle missed | Search runs on the decompressed fragment automatically; ensure the needle is within the `stream_cut` window. |

## 18. API cheat sheet

```python
from bulk_http import Engine, EngineConfig, Request, Result, sources, sinks

# Engine(**engine_config_fields) or Engine(EngineConfig(...))
engine = Engine(
    workers="auto",
    concurrency_per_worker=450,
    chunk_size=1000,
    impersonate="chrome",
    stream_cut=None,
    cut_on="wire",
    fast_status=False,
    accept_encoding="impersonate",
    http_version="auto",
    verify_ssl=True,
    follow_redirects=False,
    max_redirects=10,
    timeout=30.0,
    total_timeout=None,
    retries=2,
    retry_non_idempotent=False,
    per_domain_rate_limit=None,
    adaptive_rate=None,  # AdaptiveRateConfig(...) for self-tuning; raises BanSuspectedError
    respect_robots=False,
    allowlist=(),
    denylist=(),
    identity_header=None,
    authorization=None,
    max_tasks_per_child=50_000,
    in_flight_batches=4,
    checkpoint=None,
)

summary = engine.run(
    source,  # any sources.* stream
    predicate=None,  # Callable[[EvalContext], bool]
    out_dir="out",
    needle=None,  # global keyword
    proxies=None,  # list[str], e.g. sources.proxy_pool("proxies.txt")
    metrics_callback=None,  # Callable[[MetricsSnapshot], None]
)
# summary: chunks, matched, skipped, out_dir, checkpoint, metrics

# sources: memory, text, csv, tsv, json, proxy_pool
# sinks:   NdjsonWorkerSink, export_csv
```
