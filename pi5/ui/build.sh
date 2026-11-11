#!/bin/sh
set -eu
task_ui=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
task_headless=OFF
task_build="$task_ui/build/native"
if [ "${1:-}" = --headless ]; then
    task_headless=ON
    task_build="$task_ui/build/headless"
    shift
fi
cmake -S "$task_ui" -B "$task_build" -DCMAKE_BUILD_TYPE=Release -DSCB_UI_HEADLESS="$task_headless" "$@"
cmake --build "$task_build" -j "${SCB_UI_JOBS:-4}"
ctest --test-dir "$task_build" --output-on-failure
