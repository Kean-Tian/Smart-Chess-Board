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
| Modify Pi 5 features or choose a chess opponent | [pi5/](pi5/README.md) |
| Modify ESP32-S3 firmware or GPIO settings, or flash the firmware | [esp32/](esp32/README.md) |
| Play on the current Mac | Double-click `SCB_Computer_Test.command` |
| Validate the software on the current Mac | `sh SCB_Computer_Test.command --check-only` |
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

This opens the opponent menu:

```text
1. Local Mode - Play with Stockfish
2. AI Mode
   1. Play with AI (OpenRouter)
   2. AI Coaching (two players)
0. Quit
```

Local Mode runs offline. AI Mode uses `OPENROUTER_API_KEY` and optionally
`OPENROUTER_MODEL` (default: `openrouter/free`). AI Mode loads the saved key from
`pi5/.openrouter-key`. On first use, paste your key at the hidden prompt; it is
remembered locally with owner-only permissions and excluded from Git. To replace
it, run `sh SCB_Computer_Test.command --set-api-key`. An `OPENROUTER_API_KEY`
environment variable overrides the saved key. Enter moves such as `e2e4`, or
`quit` to exit.

**AI Coaching** is a two-human game. White and Black each choose `on` or `off`.
On an enabled player's turn, including the opening turn, OpenRouter recommends
a legal move with one short English sentence (at most 20 words). After each accepted human move,
the next player's setting controls the next hint. Players enter their own moves;
recommendations never update the board. Both OFF needs no API key or network.
During play use `coach white on/off`, `coach black on/off`, `coach` (settings),
or `hint` (retry on an enabled turn). An unavailable hint does not end the game.

You can also run `python3 scripts/play_ai.py` to open the same menu. On the Mac,
the program can use the bundled rules library and engine. On the Pi, run setup
first; `SCB_RULES_LIBRARY` can select a specific compiled rules library.

To skip the menu, pass `--opponent local` or `--opponent openrouter` to the Mac
entry point. To start coaching directly, use
`sh SCB_Computer_Test.command --coaching --coach-white off --coach-black on`.
For nine automated test suites and real local-engine checks:

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
Stockfish games do not require a network connection or an API key. OpenRouter games require an Internet connection and API credentials; automated cloud tests use simulated responses. Motion support remains at the bench-control stage, without automatic homing, obstacle avoidance, or complete capture-piece handling.

Third-party source code and licenses are kept under `engines/` and `vendor/` in the Pi directory for offline operation and rebuilding.
The old Pi direct-GPIO program and duplicate source files have been removed. The OpenRouter opponent is integrated alongside Stockfish in the current application. A complete pre-cleanup copy is stored outside the project.
