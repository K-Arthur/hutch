#!/bin/sh
# Thin wrapper for the documented command; the checks live in
# scripts/validate_responsive.py (Python + Playwright, matching the repo).
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/validate_responsive.py" "$@"
