"""Minimal example: fetch a list of URLs and keep those containing a keyword.

Run with a `targets.txt` file (one URL per line) in the working directory:

    python examples/quickstart.py
"""

from __future__ import annotations

from bulk_http import Engine, sources


def main() -> None:
    engine = Engine(
        workers="auto",
        impersonate="chrome",
        stream_cut=15_000,  # only read the first ~15 KB of each response
    )
    summary = engine.run(
        sources.text("targets.txt"),
        needle="admin",
        out_dir="out",
    )
    print(
        f"processed {summary.chunks} batches, "
        f"{summary.matched} matched, {summary.skipped} skipped -> {summary.out_dir}"
    )


if __name__ == "__main__":  # required under the spawn start method
    main()
