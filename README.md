# Smart Chessboard

Portable C++17 starting point for the Smart Chess Board software. The project
contains a host-side chess rules prototype and a hardware-independent MCU input
controller that can be tested on a desktop before connecting hardware.

## Build

```sh
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
./build/scb_console
```

Enter moves in UCI coordinate notation, such as `e2e4`; promotions append a
piece letter, such as `e7e8q`.

## Current scope

The rules core validates legal chess moves, including king safety, check,
checkmate, stalemate, castling, en passant, and promotion. It is a prototype,
not yet a certified tournament rules engine. Threefold repetition, the
50-move draw rule, and insufficient-material draws are not implemented.

The firmware controller scans 64 abstract Hall inputs, debounces changes,
tracks a lifted piece until it is placed on another square, and reports sensor
and move events as UART text lines. Its desktop test uses a push button to
toggle simulated Hall inputs; this verifies the firmware logic without waiting
for the physical board.

UART event examples:

```text
SCB1 SENSOR e2 0
SCB1 SENSOR e4 1
SCB1 MOVE e2 e4
```

## Hardware direction

The Hackster reference separates high-level chess/game decisions on a host from
low-level stepper, electromagnet, Hall homing, and LED control on a controller.
`firmware/include/scb/mcu_controller.hpp` defines the platform callbacks for
button input, Hall inputs, a status LED, and UART output. The controller logic
is implemented in `firmware/src/mcu_controller.cpp`; a concrete board adapter
still needs to map those callbacks to the selected MCU SDK and pins.

The MCU model, pinout, Hall sensor polarity, motor driver, LED driver, and
mechanism limits have not been selected yet. Motor motion, homing, board
verification, and Raspberry Pi communication commands therefore remain to be
implemented after those hardware decisions are available.
