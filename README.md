# bulk_http

A massive asynchronous, multiprocess HTTP execution engine for Python.

`bulk_http` sends, analyses and conditionally filters millions of HTTP requests
in minimal time, while keeping memory usage constant regardless of input size. It
pairs a native C networking core (libcurl-impersonate via curl_cffi) with
browser-fingerprint impersonation, multiprocess distribution, on-the-fly response
evaluation, proxy management and crash-safe, resumable output.

## Why

Standard Python HTTP stacks collapse at the multi-million request scale:

- Thread pools over synchronous clients drown the OS in context switches.
- Loading whole input files or accumulating results in memory ends in OOM.
- Full response bodies are downloaded even when a few kilobytes would do.
- Default TLS/HTTP2 fingerprints are trivially detected and blocked.

`bulk_http` addresses each of these with lazy streaming ingestion, early network
abort, a compiled networking core and process-level parallelism. Memory scales
with concurrency × workers, never with input size.

## Installation

```bash
pip install bulk_http
```

Requires Python 3.11+. On POSIX, `uvloop` is used automatically when available.

## Quick start

```python
from bulk_http import Engine, sources

if __name__ == "__main__":  # required under the spawn start method
    engine = Engine(workers="auto", impersonate="chrome", stream_cut=15_000)
    summary = engine.run(sources.text("targets.txt"), needle="admin", out_dir="out")
    print(summary)
```

Results are written as newline-delimited JSON (one file per worker) under
`out/`. Re-running with the same `checkpoint=` resumes where a run left off.

## Sources

All sources stream lazily — the whole input is never held in memory:

```python
from bulk_http import sources

sources.memory(["https://a.com", "https://b.com"])  # list of URLs or Request objects
sources.text("urls.txt")  # one URL per line
sources.csv("targets.csv", mapping={"url": 0, "needle": 1, "keep": [2, 3]})
sources.tsv("targets.tsv", mapping={"url": 0})
sources.json("targets.jsonl")  # one JSON object per line
```

The CSV/TSV `mapping` links request attributes to column indices; `"keep"`
preserves extra columns as metadata (reinjected into the output). A `Request`
object can override any engine default per line (method, headers, cookies, body,
needle, proxy, stream-cut, …).

## Filtering

Conditions combine with AND; a response is kept only if all configured checks
pass:

- **Status** — `Request(expected_status=200)` or a set `frozenset({200, 301})`.
- **Keyword** — a global `needle=` on `run`, or per-URL `needles=` on a request;
  matched with Aho-Corasick over the decompressed fragment.
- **Predicate** — a callable over a typed context:

```python
engine.run(
    source,
    predicate=lambda ctx: ctx.type == "json" and ctx.data.get("admin") is True,
)
```

The predicate context exposes `type` (`json`/`html`/`text`), `data` (parsed JSON),
`dom` (a selectolax HTML tree), `text`, `status`, `headers`, `url` and `meta`.

## Reading less: Fast-Status and Stream-Cut

- `fast_status=True` — abort after headers, never reading the body.
- `stream_cut=15_000` — abort once 15 KB have been received. `cut_on="wire"`
  (default) counts received (compressed) bytes to minimise proxy bandwidth;
  `cut_on="decoded"` counts decompressed bytes. Truncated fragments are
  decompressed tolerantly before searching.

## Proxies

```python
from bulk_http import Engine, sources

engine.run(source, proxies=sources.proxy_pool("proxies.txt"))
```

The pool round-robins over healthy proxies; a per-proxy circuit breaker
quarantines a proxy on a sustained transport-failure rate and backs off on 429,
while origin statuses (403/5xx) are blamed on the target, not the proxy. A fixed
proxy can also be set per request via `Request(proxy=...)`, and a rotating
gateway with sticky sessions is available (`bulk_http.proxies.BackconnectGateway`).

## Crash-safe output and resume

Each worker appends to its own NDJSON file. A batch is only committed to the
checkpoint manifest after its output is flushed and `fsync`ed, so a crash never
loses committed data or double-counts it. Resuming truncates each file back to
its committed offset and replays only the pending batches:

```python
engine = Engine(checkpoint="campaign.ckpt")
engine.run(source, out_dir="out")  # interrupt any time…
engine.run(source, out_dir="out")  # …and re-run to resume exactly once
```

Convert the NDJSON to CSV at the end with `bulk_http.sinks.export_csv`.

## Responsible use

`bulk_http` is intended for use within an authorised scope (assets you own,
bug-bounty programs with an explicit scope, internet-measurement research). It
provides the technical means for compliant use:

- `denylist=` / `allowlist=` of domains (matching a host and its subdomains).
- `per_domain_rate_limit=` requests per second per host.
- `identity_header=("X-Contact", "you@example.com")` for a contactable scan.
- `authorization="scope reference"` attached to every output record.
- `bulk_http.compliance.RobotsCache` for `robots.txt` rules and crawl-delay.

Legal responsibility for how the library is used rests with the user.

## HTTP/3

HTTP/3 is opt-in per request via `http_version="h3"` and requires a QUIC-capable
libcurl build (detected at runtime) and a UDP-capable proxy for proxied traffic;
the default (`"auto"`) negotiates HTTP/2 or HTTP/1.1.

## Platform notes

Windows is a first-class target. Because its selector event loop caps sockets per
process, concurrency is reached by scaling out worker processes rather than
raising per-process concurrency; the reliable Selector loop is the default, with
an opt-in `winloop` path pending validation.

## Development

```bash
uv sync --extra dev
./scripts/check.sh   # ruff lint + format check, mypy (strict), pytest with coverage
```

See `examples/` for runnable scripts.

## License

MIT — see [LICENSE](LICENSE).
