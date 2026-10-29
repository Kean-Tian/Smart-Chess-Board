#!/bin/sh
set -eu
export PYTHONDONTWRITEBYTECODE=1
task_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$task_root"
task_python="$task_root/.venv/bin/python"
if [ ! -x "$task_python" ]; then task_python=python3; fi
task_mode=play
case "${1:-}" in test|--self-test|play|board) task_mode=$1; shift ;; esac
case "$task_mode" in
    test|--self-test) exec "$task_python" app/stockfish_engine.py --self-test "$@" ;;
    play) exec "$task_python" app/play.py "$@" ;;
    board) exec "$task_python" app/play.py --board "$@" ;;
    *) echo "Usage: sh start.sh [play|test|board] [options]" >&2; exit 2 ;;
esac
