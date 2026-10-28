# Smart Chess Board

Team 24. The ESP32-S3 controls the chessboard hardware; the Raspberry Pi 5 runs the chess rules, Stockfish, and application software.

## Git LFS Setup

The bundled Stockfish executables are stored with Git LFS. Install Git LFS before cloning this repository. If you already cloned it, run the following commands from the project root to download the actual engine files:

```sh
git lfs install
git lfs pull
```

## Getting Started

| Task | Start here |
|---|---|
| Modify Pi 5 features or run Stockfish | [pi5/](pi5/README.md) |
| Modify ESP32-S3 firmware or GPIO settings, or flash the firmware | [esp32/](esp32/README.md) |
| Validate the software on the current Mac | Double-click `SCB_Computer_Test.command` |
| View PCB schematics and the KiCad project | [hardware/](hardware/README.md) |
| Check GPIO and ribbon-cable mappings | [Connection map](docs/PCB_Connection_Map.md) |
| Check Pi–MCU commands and messages | [USB protocol](docs/USB_Protocol.md) |

## Directory Structure

```text
SCB/
├── pi5/                       Pi 5 application, rules, Stockfish, dependencies, and tests
│   ├── app/                   Python applications and USB client
│   ├── rules/                 C/C++ rules interface, Python wrapper, and console
│   ├── engines/stockfish/     Official ARM64 engine, source code, and license
│   ├── vendor/                libchess and offline Python wheels
│   ├── tests/
│   ├── setup.sh               Initial setup on the Pi
│   └── start.sh               Startup on the Pi
├── esp32/                     Standalone ESP-IDF / PlatformIO firmware project
│   ├── main/                  GPIO configuration, control logic, and platform drivers
│   ├── components/board_logic/  Debouncing, move events, and LED square mapping
│   ├── tests/                 Control-logic tests without hardware
│   └── release/               Compiled firmware and flash-address manifest
├── hardware/                  PCB PDFs and the existing KiCad connector project
├── docs/                      Interfaces, wiring, and validation records
├── tools/mac_test/            Mac test tools and Mac-specific binaries
├── SCB_Computer_Test.command  Test / chess entry point for the current Mac
└── CMakeLists.txt             Unified host build and test entry point
```

On the Mac, open Terminal, change to this directory, and run:

```sh
sh SCB_Computer_Test.command
```

This runs six test suites, then starts a local game against the computer. Enter moves such as `e2e4`, or enter `quit` to exit. For automated checks only:

```sh
sh SCB_Computer_Test.command --check-only
```

## All Host Tests

Requires CMake, a C/C++ compiler, and a Python interpreter with the same architecture as the compiler output:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=/usr/bin/python3
cmake --build build -j 4
ctest --test-dir build --output-on-failure
```

This entry point builds only the Pi rules library and host tests. Cross-compile the ESP32 firmware separately in `esp32/`.

## Current Validation Scope and Limitations

Software tests and firmware builds have been performed. The Pi 5, physical USB link, GPIO, motors, and sensors have not been connected to this Mac for hardware validation.
Stockfish games do not require a network connection or an API key. Motion support remains at the bench-control stage, without automatic homing, obstacle avoidance, or complete capture-piece handling.

Third-party source code and licenses are kept under `engines/` and `vendor/` in the Pi directory for offline operation and rebuilding.
The old Pi direct-GPIO program, the cloud-opponent example replaced by Stockfish, duplicate source files, and old build caches have been removed from the working directory. A complete pre-cleanup copy is stored outside the project.
