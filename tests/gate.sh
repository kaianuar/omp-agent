#!/usr/bin/env bash
# GATE 1 — hard test gate. Exit 0 = pass (may proceed), non-zero = FAIL (must fix).
# This is the "real tests" gate PIPELINE.md refers to. omp sees the exit code.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> GATE 1: running test suite..."

# ============================================================
# RUN TESTS — edit this section for your project's test runner
# ============================================================
# Example (Node/Jest):
#   npm test -- --runInBand
# Example (Python/pytest):
#   python -m pytest -q
# Example (Vitest, AfterQuery-style):
#   npx vitest run --reporter=json --outputFile=test-results.json
exit 0  # <-- replace with the actual test command. Keep non-zero on failure.
# ============================================================

echo "==> GATE 1 passed."
