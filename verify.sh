#!/usr/bin/env bash
# Verify the plyunit workspace: Python env, raylib, native C extensions.
# Usage: ./verify.sh
set -euo pipefail
cd "$(dirname "$0")"

uv run python scripts/verify_install.py
