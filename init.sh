#!/usr/bin/env bash
# Bootstrap the plyunit workspace after cloning: sync all deps (builds the
# native C extension), verify the install, then optionally run an example.
#
# Usage:
#   ./init.sh                # setup + verify, print how to run examples
#   ./init.sh --shapes       # setup + verify + run `examples/cli.py --shapes`
#   ./init.sh --list         # setup + verify + list available examples
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Syncing workspace (uv sync)"
# Root project pulls in plyunit[all] (incl. plyunit-native) + dev group.
# plyunit-native compiles plyunit._plyunit_batch / plyunit._fb_fast when a
# C compiler is present and copies the .pyd/.so into packages/plyunit/src.
uv sync

# If the C extensions are still missing (uv cache hit from a toolchain-less
# build), force a rebuild of plyunit-native.
if ! uv run --no-sync python -c "import plyunit._plyunit_batch, plyunit._fb_fast" 2>/dev/null; then
    echo "==> Native extension missing; rebuilding plyunit-native"
    uv sync --reinstall-package plyunit-native
fi

echo "==> Verifying install"
./verify.sh

if [ "$#" -gt 0 ]; then
    echo "==> Running example: $*"
    exec uv run python examples/cli.py "$@"
fi

echo ""
echo "Workspace ready. Next steps:"
echo "  uv run python examples/cli.py --list          # list examples"
echo "  uv run python examples/cli.py --shapes        # run an example"
echo "  ./new_project.sh my_project                   # scaffold a project in projects/"
