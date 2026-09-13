#!/usr/bin/env bash
# Run the full quality gate: lint, format check, type check and tests+coverage.
set -euo pipefail

echo "==> ruff check"
ruff check .

echo "==> ruff format --check"
ruff format --check .

echo "==> mypy"
mypy

echo "==> pytest + coverage"
pytest --cov=bulk_http --cov-report=term-missing --cov-fail-under=90

echo "All checks passed."
