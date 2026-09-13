# bulk_http

A massive asynchronous, multiprocess HTTP execution engine for Python.

`bulk_http` is built to send, analyse and conditionally filter millions of HTTP
requests (reference target: 3,000,000 URLs) in minimal time, while keeping memory
usage constant regardless of input size. It combines a native C networking core
with browser fingerprint impersonation, multiprocess distribution, on-the-fly
response evaluation, proxy management and crash-safe resumption.

## Why

Standard Python HTTP stacks collapse at the multi-million request scale:

- Thread pools over synchronous clients drown the OS in context switches.
- Loading whole input files or accumulating results in memory ends in OOM.
- Full response bodies are downloaded even when a few kilobytes would do.
- Default TLS/HTTP2 fingerprints are trivially detected and blocked.

`bulk_http` addresses each of these with lazy streaming ingestion, early network
abort, a compiled networking core and process-level parallelism.

## Features

- **Streaming ingestion** from in-memory lists, text, CSV/TSV and JSON — never
  loading the whole input at once.
- **Fast-Status** and **Stream-Cut**: abort transfers at the network level once
  headers or a byte threshold are reached.
- **Conditional evaluation**: HTTP status matching, multi-pattern search and a
  user-supplied predicate over typed JSON/HTML/text context.
- **Fingerprint impersonation** of real browsers (TLS/HTTP2).
- **Proxy management**: pools, rotating gateways, per-request overrides,
  circuit breaking and per-domain rate limiting.
- **Crash-safe output**: per-worker NDJSON with transactional, per-batch
  checkpointing and resumable campaigns.

## Installation

```bash
pip install bulk_http
```

## Quick start

```python
from bulk_http import Engine, sources, sinks

engine = Engine(workers="auto", impersonate="chrome", stream_cut=15_000)
results = engine.run(
    source=sources.csv("targets.csv", mapping={"url": 0, "needle": 1}),
    predicate=lambda ctx: ctx.type == "html" and ctx.dom.css_first("title") is not None,
    sink=sinks.ndjson_per_worker("out/"),
)
```

## Responsible use

`bulk_http` is intended for use within an authorised scope (assets you own,
bug-bounty programs with an explicit scope, internet-measurement research). It
provides technical means for compliant use — `robots.txt` support, per-domain
rate limiting, allow/deny lists and a configurable identity header. Legal
responsibility for how it is used rests with the user.

## License

MIT — see [LICENSE](LICENSE).
