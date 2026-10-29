#!/bin/sh
set -eu
export PYTHONDONTWRITEBYTECODE=1
task_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$task_root"
if [ "$(uname -s)" != Darwin ]; then
    echo "此入口用于 Apple Silicon Mac。Pi 请使用 pi5/setup.sh 和 pi5/start.sh。" >&2
    exit 1
fi
if [ -x "$task_root/tools/mac_test/binaries/stockfish-macos-universal" ]; then
    export STOCKFISH_EXECUTABLE="$task_root/tools/mac_test/binaries/stockfish-macos-universal"
fi
export SCB_RULES_LIBRARY="$task_root/tools/mac_test/binaries/libscb_rules.dylib"
if [ "${1:-}" = --check-only ]; then
    exec /usr/bin/arch -arm64 /usr/bin/python3 tools/mac_test/check_software.py
fi
exec /usr/bin/arch -arm64 /usr/bin/python3 pi5/app/play.py "$@"
