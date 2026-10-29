# Pi 5 Software

This directory contains all Pi-side runtime code and dependencies and can be copied to the Pi 5 on its own.
Use **64-bit Raspberry Pi OS Bookworm or later**.

## Run

On the Pi, change to this directory:

```sh
sh setup.sh
sh start.sh
```

`setup.sh` creates a Python environment, builds the rules library using the bundled dependencies, runs eight Pi software test suites, and then checks the local Stockfish engine. OpenRouter opponent and coaching tests use simulated responses.
A network connection is needed to install system build tools if they are not already installed. Stockfish, libchess source code, and the pyserial wheel are included in this directory.

Entry points:

```sh
sh start.sh test
sh start.sh
sh start.sh play --opponent local --skill 10 --movetime 500
sh start.sh play --opponent openrouter
sh start.sh play --coaching --coach-white off --coach-black on
sh start.sh board --port /dev/ttyACM0
```

- `test`: checks Stockfish communication and moves; no ESP32 is required.
- `play` (default): opens a menu with **Local Mode** (Stockfish), **AI Mode → Play with AI** (OpenRouter), and **AI Mode → AI Coaching** (two humans). Accepts UCI moves from the keyboard; enter `quit` to exit. `--opponent local|openrouter` skips the opponent menu; `--coaching` starts coaching setup directly.
- `board`: opens the same opponent menu, then receives ESP32 board events. Computer moves are indicated by LEDs and confirmed through occupancy after manual execution. This mode does not automatically ARM or move the motors. You can also pass `--opponent local|openrouter`.
- `--computer white` lets the computer play White; the default is Black.
- `--skill 0..20` sets playing strength; `--movetime 50..10000` sets the target search time in milliseconds per move.

`--skill` and `--movetime` configure Local Mode only. AI Mode keeps the original
OpenRouter chat-completions method. Configure it in Terminal:

```sh
sh start.sh play --opponent openrouter
```

AI Mode automatically loads the key from `pi5/.openrouter-key` (relative to the
project root). If no saved key or `OPENROUTER_API_KEY` is available, the interactive
Terminal asks for hidden input. Paste the key once and press Enter; the key is
saved with file permissions `0600` and is ignored by Git. The environment variable
overrides the saved key. To replace the saved key, run
`sh start.sh --set-api-key`. `OPENROUTER_MODEL` selects the model.

### AI Coaching

Choose **AI Mode → 2. AI Coaching**. White and Black each choose `on` or `off`.
All four combinations are supported independently. Both OFF is ordinary PvP
and never creates an AI client, asks for a key, or sends an API request.

At each enabled player's turn, including the first turn, the coach recommends
one legal UCI move and explains it in one short English sentence, at most 20
words. After a human move is
accepted, the next player's setting determines whether a new hint is requested.
The hint never moves a piece; both players enter their own moves at `White >`
and `Black >`, and can choose any legal move.

- `coach white on` / `coach white off`: change White's setting.
- `coach black on` / `coach black off`: change Black's setting.
- `coach`: display both settings.
- `hint`: request another hint for the current player, only if enabled.
- `quit`: end the game.

Use `--coach-white on|off` and `--coach-black on|off` to supply settings without
prompts. These flags also select coaching directly. Illegal moves do not trigger
duplicate automatic hints. If a request fails, the humans can continue playing
or use `hint` to retry. A finished game makes no further coaching requests.

The physical-board entry also supports `sh start.sh board --coaching`. It waits
for initial synchronization and complete physical confirmation before coaching
the next player. Coaching does not ARM or operate motors.

`--model <model-id>` overrides `OPENROUTER_MODEL`. Both modes can play either color
and must pass the same rules validation. OpenRouter gets the current FEN and legal
moves and has up to three attempts with a 120-second timeout per request. On
failure, keyboard play preserves the position and offers retry or quit. Physical
board play waits for the `retry` command. A missing API key in a noninteractive
session fails before starting the game; AI Mode does not start Stockfish.

API reference: [OpenRouter chat completions](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion).

If the response cannot be parsed, the error reports its HTTP status, media type,
compression and byte count without printing the response body or API key. An
HTML response suggests a network/proxy, sign-in or block page; an empty or
malformed JSON response can be retried. The client requests JSON with identity
encoding and can also decode gzip/deflate replies. API errors report account or
model error codes even when the HTTP status is 200. After changing the software,
exit and restart the console before testing again.

## File Responsibilities

| Location | Purpose |
|---|---|
| `app/board_game.py` | Physical board synchronization, move legality, and PvP/PvC game flow |
| `app/scb_link.py` | USB requests, events, and heartbeat |
| `app/stockfish_engine.py` | Local UCI engine process |
| `app/openrouter_engine.py` | OpenRouter opponent, response validation, and bounded retries |
| `app/play.py` | Local / AI Mode menu and keyboard / physical-board launcher |
| `app/coaching.py` | Two-human play, independent side settings, and optional coaching hints |
| `app/play_stockfish.py` | Shared keyboard game loop; direct invocation defaults to local play |
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

The Pi maintains the chess rules and logical board state. Both Stockfish and OpenRouter results must pass rules validation. After an illegal move, the physical board must be restored. Use `commit <uci>` to resolve promotions or ambiguous multi-square changes; matching occupancy is still required.
This directory does not access Pi GPIO. All hardware operations are sent through the ESP32 USB protocol.

Official references: [Stockfish 19](https://github.com/official-stockfish/Stockfish/releases/tag/sf_19), [UCI](https://official-stockfish.github.io/docs/stockfish-wiki/UCI-Protocol-and-Stockfish-Commands.html).
