# Pi 5 Software

This directory contains all Pi-side runtime code and dependencies and can be copied to the Pi 5 on its own.
Use **64-bit Raspberry Pi OS Bookworm or later**.

## Run

On the Pi, change to this directory:

```sh
sh setup.sh
sh start.sh
```

`setup.sh` creates a Python environment, builds the rules library using the bundled dependencies, runs five Pi software test suites, and then checks the local Stockfish engine.
A network connection is needed to install system build tools if they are not already installed. Stockfish, libchess source code, and the pyserial wheel are included in this directory.

Entry points:

```sh
sh start.sh test
sh start.sh play --skill 10 --movetime 500
sh start.sh board --port /dev/ttyACM0
```

- `test`: checks Stockfish communication and moves; no ESP32 is required.
- `play` (default): accepts UCI moves from the keyboard for games against local Stockfish. Enter `quit` to exit.
- `board`: receives ESP32 board events. Stockfish moves are indicated by LEDs and confirmed through occupancy after manual execution. This mode does not automatically ARM or move the motors.
- `--computer white` lets the computer play White; the default is Black.
- `--skill 0..20` sets playing strength; `--movetime 50..10000` sets the target search time in milliseconds per move.

## File Responsibilities

| Location | Purpose |
|---|---|
| `app/board_game.py` | Physical board synchronization, move legality, and PvP/PvC game flow |
| `app/scb_link.py` | USB requests, events, and heartbeat |
| `app/stockfish_engine.py` | Local UCI engine process |
| `app/play_stockfish.py` | Games against the computer without hardware |
| `rules/src/` | libchess C interface and command-line console |
| `rules/include/` | Rules interface headers |
| `rules/python/scb_rules.py` | Python rules wrapper and move history |
| `engines/stockfish/` | Official Stockfish 19 ARM64 executable and corresponding source code |
| `vendor/` | Pinned libchess version and offline Python dependencies |
| `tests/` | Automated tests for the Pi software |
| `runtime/` | Records generated when running on the Pi (ignored automatically) |

## Build Only the Rules Library

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 2
ctest --test-dir build --output-on-failure
```

The shared library is placed in `build/lib/`, and the console in `build/bin/`. The Python wrapper checks that library location first; set `SCB_RULES_LIBRARY` to use a specific library file.
Set `STOCKFISH_EXECUTABLE` to select a Stockfish executable for another platform. The Pi defaults to the bundled Linux ARM64 version; the entry point for the current Mac is in the project root.

The Pi maintains the chess rules and logical board state. Stockfish results must pass rules validation. After an illegal move, the physical board must be restored. Use `commit <uci>` to resolve promotions or ambiguous multi-square changes; matching occupancy is still required.
This directory does not access Pi GPIO. All hardware operations are sent through the ESP32 USB protocol.

Official references: [Stockfish 19](https://github.com/official-stockfish/Stockfish/releases/tag/sf_19), [UCI](https://official-stockfish.github.io/docs/stockfish-wiki/UCI-Protocol-and-Stockfish-Commands.html).
