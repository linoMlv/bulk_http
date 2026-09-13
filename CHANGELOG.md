# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-09-13

### Added
- Streaming input sources: in-memory, text, CSV/TSV (with column mapping and
  preserved metadata) and JSON Lines.
- Tolerant partial decompression of gzip, deflate, brotli and zstd fragments.
- Conditional evaluation: HTTP status matching, Aho-Corasick keyword search and
  a user predicate over a typed JSON/HTML/text context.
- curl_cffi networking core with browser fingerprint impersonation, Fast-Status
  and Stream-Cut early network abort, and method-aware retries with backoff.
- Proxy management: health-aware pool, backconnect gateway with sticky sessions,
  per-proxy circuit breaker and per-domain rate limiting.
- Multiprocess distribution (spawn) with cloudpickled predicates, bounded
  backpressure and worker recycling; OS-appropriate event loop selection.
- Crash-safe output: per-worker NDJSON with transactional per-batch checkpointing
  and exactly-once resume, plus CSV export.
- Observability: campaign metrics aggregated across workers (throughput, latency
  percentiles, status distribution, error counts), exposed on `RunSummary.metrics`
  and via a `metrics_callback`.
- Responsible-use guardrails: allow/deny lists, identity header, authorization
  note, per-domain rate limiting, and enforced `robots.txt` (`respect_robots`,
  off by default) with crawl-delay.
- Per-URL `total_timeout` budget spanning retries and backoffs.
- Optional adaptive (AIMD) per-domain rate limiting that self-tunes toward a
  sustainable rate; transient failures are deferred and replayed in later passes
  once the rate has converged, and `BanSuspectedError` stops the run when failures
  persist at the minimum rate.
- Opt-in HTTP/3 (availability-detected) and an opt-in winloop path.

[0.1.0]: https://github.com/linoMlv/bulk_http/releases/tag/v0.1.0
