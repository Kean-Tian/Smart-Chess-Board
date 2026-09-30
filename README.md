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

The selected architecture uses a Raspberry Pi 4 Model B for high-level game
logic and a Raspberry Pi Pico 2 for real-time embedded control. The Pi-side
UART bridge is in `pi/src/uart_bridge.cpp`; it reads sensor/move events from
`/dev/serial0` and checks physical moves using the chess-rules core.

The portable controller is in `firmware/src/mcu_controller.cpp`. The Pico 2
adapter in `firmware/pico/main.cpp` currently runs button-test mode: an external
button simulates Hall-input changes and UART0 reports them at 115200 baud. See
`firmware/pico/README.md` for SDK build steps and UART wiring.

The 64 Hall inputs are not connected yet. Their multiplexer/shift-register
topology, sensor polarity, stepper driver, LED driver, homing switches, and
mechanical limits still need to be selected before implementing board scanning
and automatic piece movement.
