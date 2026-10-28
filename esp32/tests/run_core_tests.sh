#!/bin/sh
set -eu
task_esp=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_build=${SCB_TEST_BUILD_DIR:-"${TMPDIR:-/tmp}/scb-core-tests"}
mkdir -p "$task_build"
${CC:-cc} -std=c17 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -Werror \
  -fsanitize="${SCB_SANITIZERS:-undefined}" -g \
  -I "$task_esp/components/board_logic/include" -I "$task_esp/main" \
  "$task_esp/tests/esp32_core_tests.c" "$task_esp/main/scb_core.c" \
  "$task_esp/components/board_logic/src/sensor_matrix.c" \
  "$task_esp/components/board_logic/src/led_grid.c" \
  -o "$task_build/esp32_core_tests"
"$task_build/esp32_core_tests"
