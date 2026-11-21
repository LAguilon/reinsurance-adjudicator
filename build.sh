#!/usr/bin/env bash
# Root convenience wrapper: build Catala + Lean and run the test suite.
set -euo pipefail
cd "$(dirname "$0")"
./scripts/build.sh
python3 tests/run_tests.py
