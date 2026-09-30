# Smart Chessboard

This repo contains the code for my smart chessboard project. The goal is to use
a Raspberry Pi 4 for the chess logic and a Raspberry Pi Pico 2 for reading the
board sensors and controlling the hardware. The Pi-side programs use
[`libchess`](https://github.com/kz04px/libchess) to check legal moves.

Right now, the project is still a prototype. The chess code and the basic Pico
input logic work, but the full sensor board and automatic piece movement are
not connected yet.

## Build and run

The desktop build needs CMake, a C17 compiler, a C++20 compiler, and Git. CMake
downloads the pinned `libchess` version automatically the first time it runs:

```sh
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
./build/scb_console
```

Moves use UCI coordinates. For example, type `e2e4` to move a piece from e2 to
e4. For promotion, add the new piece at the end, such as `e7e8q`.

## What works so far

The `libchess` rules adapter checks normal legal moves as well as check,
checkmate, stalemate, castling, en passant, promotion, threefold repetition,
and the 50-move draw rule. Insufficient-material draws are not handled yet.

The MCU controller can scan 64 Hall-sensor inputs, debounce them, and follow a
piece from the square where it was picked up to the square where it was placed.
For now, a push button is used to fake sensor changes, so the firmware logic can
be tested before the real board is wired up.

The UART output looks like this:

```text
SCB1 SENSOR e2 0
SCB1 SENSOR e4 1
SCB1 MOVE e2 e4
```

## Raspberry Pi and Pico

The Raspberry Pi side is in `pi/src/uart_bridge.c`. It reads the Pico's UART
messages from `/dev/serial0` and sends completed moves through the C-compatible
`libchess` adapter for validation.

The shared controller code is in `firmware/src/mcu_controller.c`, and the Pico
2 entry point is in `firmware/pico/main.c`. The Pico currently runs in button
test mode and sends messages over UART0 at 115200 baud. Build instructions and
wiring details are in `firmware/pico/README.md`.

## Still to do

The 64 Hall sensors still need a final multiplexer or shift-register layout.
The stepper driver, LED driver, homing switches, sensor polarity, and mechanical
limits also need to be decided before the board can scan real pieces and move
them automatically.
