# Smart Chessboard

Portable C++17 starting point for the SCB software. The current prototype keeps
chess rules independent of the eventual MCU, motor drivers, sensors, and LED
implementation. Build and test it on a desktop before connecting hardware.

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

## Hardware direction

The Hackster reference separates high-level chess/game decisions on a host from
low-level stepper, electromagnet, Hall homing, and LED control on a controller.
This project starts with a portable rules core; the next hardware-facing layer
should expose commands such as `move piece from square A to square B`, then
implement them behind a board-I/O interface for the selected MCU and drivers.
No MCU, pinout, motor driver, or board sensing method has been selected yet, so
hardware-specific code is intentionally not assumed here.
