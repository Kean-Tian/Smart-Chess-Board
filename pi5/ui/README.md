# Smart Chess Board touchscreen application

Native **C / LVGL 9.3 / SDL2** UI for Raspberry Pi 5 and the **5-inch Touch Display 2, 720 x 1280 portrait**. A local Python service owns the USB serial connection, authoritative chess rules, Stockfish worker, clocks and SQLite game records. The UI communicates through a private Unix socket; it does not update widgets from background threads.

There are no seed players, invented statistics, sample games or preset hint moves. Players and games are read from SQLite. A static starting-board diagram is a target layout, not a reported sensor measurement. Without fresh hardware data, occupancy is unavailable and Start remains disabled.

## Install and launch

From the project root on 64-bit Raspberry Pi OS:

```sh
sh pi5/ui/setup.sh
sh pi5/start.sh ui
```

The installer prepares the existing Pi Python environment, compiles the native chess-rules library, verifies the bundled ARM64 Stockfish, installs SQLite/SDL2 development libraries, builds the UI and runs checks. The first installation needs Internet access for apt and pinned LVGL. Completion does not automatically launch the application: use the second command.

The launcher starts the local game service and then the UI. Escape closes the UI; the service saves an unfinished active game as interrupted. Only one UI/controller should run at a time. For a smaller desktop window:

```sh
sh pi5/start.sh ui --window
```

After source changes, rerun setup.sh when backend/dependencies changed. For C-only changes use `sh pi5/ui/build.sh`. Use the launcher rather than starting the C binary alone, otherwise the game service is absent.

## First actual game

1. In **Players**, create saved profiles. PvP and Coaching require two different players; PvC needs one human profile.
2. Close any existing serial terminal for the board. Connect ESP32-S2-Saola-1 to the Pi with a data USB cable, using the existing tested sensor connections and power supply.
3. Open **Diagnostics**, choose the actual USB serial port, then **Connect board**. Only an explicitly chosen/configured device is opened.
4. Check actual occupancy using a1, h1, a8 and h8. Coordinates are used exactly as reported by the firmware. The UI does not rotate or mirror occupancy or moves; previously saved rotation settings are ignored. MUX details remain raw as-wired values.
5. Open **New game**. Choose mode, tap White/Black to assign real players, select the human side for PvC, and choose 5 minutes, 10 minutes or no clock.
6. Select **Set up the board**, arrange the standard position, then **Check position**. A recent matching full-board occupancy frame is required.
7. Manually verify piece types, colors and board orientation, then select the verification button. Hall occupancy cannot identify piece identity. Only then can **Start game** run.
8. Play on the physical board. A candidate move advances the logical game only after rules validation and matching physical occupancy. The accepted move, resulting FEN and remaining clocks are saved transactionally.

No computer or UI operation automatically arms motors or energizes the magnet. In computer mode Stockfish returns a real legal move; follow the displayed move on the board manually. Optional external LED feedback must be enabled explicitly in Diagnostics.

## New game and Active Game

- **Two players:** two saved human players. The Pi validates physical moves.
- **Vs computer:** a saved human plays White or Black against the actual local Stockfish process. Searches run in a worker, while scanning, clocks, pause and navigation remain responsive. Default search time is 2 seconds; the existing engine wrapper enforces its response budget.
- **With coaching:** two saved humans with local Stockfish move recommendations for the player to move. Hints are generated from the current legal position and never move a piece. No API key or cloud request is required. The separate existing terminal/OpenRouter coaching code is unchanged.
- **Time control:** both clocks are maintained by the service using monotonic time, independent of the currently displayed page. They switch only after an accepted physical move.
- **Pause / Resume:** clocks stop; sensor diagnostics continue. Moves are not committed during pause. Resume requires reconnection and synchronization with the accepted position.
- **End:** Cancel keeps the game. Confirmation records White win, Black win, Draw or End without a result, as selected by the players. Rules-detected checkmate/draw stores its actual result automatically.
- **Clock expiry:** pauses the game and asks the players to confirm the outcome; it does not invent a FIDE timeout result without complete material adjudication.
- **Hint:** requests a real local Stockfish recommendation; failure is displayed without manufacturing a replacement hint.
- **Confirm move:** enter UCI, such as `e2e4`, when sensor changes are ambiguous. The same legality and matching-occupancy checks still apply. Promotions require a piece choice. Castling waits for the complete king/rook occupancy change.
- **View current position:** opens the last recorded position without altering the live game, useful when restoring an illegal move. Back returns to Active Game. Clocks continue while viewing unless paused.

Board disconnect, stale sensor data or local UI-controller loss pauses an active game. Reconnection never silently resumes clocks or accepts an unverified position. An engine error does not fabricate a move. A failed SQLite move write does not advance the logical position.

## Diagnostics

Actual data only:

- USB port selection, connection/disconnection and explicit scan request.
- Fresh 64-square occupancy; absent/stale data is unavailable, not an empty board.
- MCU-measured full-frame scan interval and debounce confirmation time.
- Raw MUX/GPIO/input trace and fault details.
- Optional external LED feedback, off by default.

The service requests periodic snapshots to establish freshness. Changed BOARD snapshots are pushed to the UI immediately; clocks/status target a 20 Hz refresh. The serial reader waits for one byte and drains available bytes, avoiding the previous wait for a 256-byte buffer. These are software scheduling choices, not measured physical end-to-end latency claims.

## SQLite players and history

Default database:

```text
~/.local/share/scb/players.sqlite3
```

`XDG_DATA_HOME`, `SCB_PLAYER_DB`, or `--database PATH` can override it. It is outside the code directory and is not included in an update.

The shared `pi5/storage/schema.sql` migrates the earlier player-only schema in place to version 2. Existing player IDs, names and selection remain. Tables contain players, selection, board settings, games and accepted moves. Each move stores the resulting FEN and both clocks. Game rows retain participant-name snapshots even if a player is renamed/deleted later.

Players support creation, selection, rename, confirmed deletion and pagination. Names are 1-24 printable ASCII characters, trimmed and unique ignoring ASCII case. The bundled font lacks Chinese glyphs; unsupported names are rejected. SQL values are bound parameters. No player is created automatically.

History lists actual active, completed and interrupted games. Review reads initial FEN or the saved position for a selected ply. Previous/Next do not ask Stockfish, roll back a live game, contact the MCU or move physical pieces. Leaving the application retains committed moves; unfinished games are marked interrupted rather than given an invented winner.

## Service and files

| File | Responsibility |
|---|---|
| `src/scb_ui.c` | Native pages, settings, widgets and main-thread updates |
| `src/ui_bridge.c` | Nonblocking Unix-socket transport and SQLite JSON decoding |
| `src/player_store.c` | C-side player persistence, using the shared schema |
| `src/main.c` | LVGL drawing, SDL mouse/touch/keyboard and test host |
| `../app/ui_launcher.py` | Start/stop one UI and its local service |
| `../app/ui_service.py` | Serial ownership, asynchronous I/O, snapshots and UI protocol |
| `../app/ui_game.py` | Legal physical moves, clocks, game state and Stockfish worker |
| `../app/game_store.py` | Transactional game records and read-only replay |
| `../storage/schema.sql` | One database schema shared by C and Python |

The socket defaults to `$XDG_RUNTIME_DIR/scb-ui.sock`, or `~/.local/share/scb/scb-ui.sock`; override with `SCB_UI_SOCKET`. It is local and user-only. The service log is next to the database as `ui_service.log`. `SCB_SERIAL_PORT` can advertise an explicitly configured serial device. Never run a separate serial console against the same board while this service is connected.

## Verification

```sh
sh pi5/ui/setup.sh
```

Checks include native rules, USB framing, actual SQLite migration/persistence, legal move acceptance, clocks, pause/resume, checkmate, captures, castling, promotions, stale/disconnected boards, failed persistence and actual Stockfish opponent/hint searches. The native UI integration test goes through widgets, a Unix socket, the real rules/SQLite service and a PTY-emulated MCU, then reopens saved replay. SDL tests cover mouse/touch fast clicks and keyboard controls at three window sizes.

Tests and screenshots use isolated temporary databases; they do not create fixtures in the user's player library. No test commands a physical motor, opens a real board or calls a network API. PTY timing/inputs are test fixtures, not measured hardware results.

The development Mac build passes these software checks. Pi ARM64 execution, actual sensor polarity/orientation, physical touch, LED wiring and end-to-end hardware latency require verification on the connected Pi and board.

`preview/index.html` is only an offline layout gallery, generated by the C renderer with an empty temporary database and no service. It contains no working database or sample games. The initial-board image is explicitly the target arrangement. Real operation requires the native launcher.

## References

- [SQLite C interface](https://www.sqlite.org/cintro.html)
- [SQLite JSON functions](https://www.sqlite.org/json1.html)
- [Official Touch Display 2 installation](https://www.raspberrypi.com/documentation/accessories/touch-display-2.html)
- [LVGL 9.3 SDL integration](https://lvgl.io/docs/open/9.3/details/integration/driver/sdl)
