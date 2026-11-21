#!/usr/bin/env bash
# Thin wrapper: run the verified bridge. No arithmetic happens here.
set -euo pipefail
cd "$(dirname "$0")/.."
exec "$HOME/.elan/bin/lake" env lean --run lean_bridge/Runner.lean "$@"
