"""Smoke tests for the package's public surface."""

import re


def test_package_is_importable_and_exposes_version() -> None:
    import bulk_http

    assert isinstance(bulk_http.__version__, str)
    assert re.fullmatch(r"\d+\.\d+\.\d+", bulk_http.__version__)
