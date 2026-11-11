#!/bin/sh
set -eu
task_ui=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
task_binary="$task_ui/build/native/scb_touch_ui"
if [ ! -x "$task_binary" ]; then sh "$task_ui/build.sh"; fi
task_pi=$(CDPATH= cd -- "$task_ui/.." && pwd)
task_python="$task_pi/.venv/bin/python"
if [ ! -x "$task_python" ]; then task_python=python3; fi
if [ "${1:-}" = --window ]; then
    shift
    exec "$task_python" -B "$task_pi/app/ui_launcher.py" --binary "$task_binary" -- "$@"
fi
exec "$task_python" -B "$task_pi/app/ui_launcher.py" --binary "$task_binary" -- --fullscreen "$@"
