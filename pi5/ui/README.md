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

The launcher starts the local game service and then the UI. The top-left Quit Game button or Escape closes the UI; the service saves an unfinished active game as interrupted. Only one UI/controller should run at a time. For a smaller desktop window:

```sh
sh pi5/start.sh ui --window
```

After source changes, rerun setup.sh when backend/dependencies changed. For C-only changes use `sh pi5/ui/build.sh`. Use the launcher rather than starting the C binary alone, otherwise the game service is absent.

## First actual game

1. In **Players**, create saved profiles. PvP and Coaching require two different players; PvC needs one human profile.
2. Close any serial terminal using the board. Connect SCB Master PCB V3 (ESP32-S3) to the Pi using a data USB cable and the tested sensor wiring/power supply.
3. Open **New game**. Choose mode, assign actual players, select the human side for PvC, and choose 5 minutes, 10 minutes or no clock. In With coaching, White and Black must each explicitly choose AI coaching ON or OFF; all four combinations, including both OFF, are allowed.
4. Open **Set up the board**. Select the USB serial port at the top and press **Connect board**. The main-menu **Board test** page can also connect the same board.
5. Arrange the standard starting position and press **Check position**. A fresh matching full-board occupancy frame is required.
6. Confirm the actual piece types and colors, then press **Start game**. Hall occupancy cannot identify piece types. Firmware coordinates are used unchanged; verify physical mapping before gameplay.
7. Play on the physical board. A move advances the game only after legality and matching occupancy checks; accepted moves and clocks are saved transactionally.

The main-menu **Board test** opens a live 64-square occupancy viewer with fixed firmware coordinates. `O` means occupied, a blank means empty, and `?` means unavailable. Tap a square to see its coordinate and state. Red borders identify differences from the current logical position, when one exists. Diagnostic display orientation is separate from firmware and game coordinates.

**Scan now** requests SCAN, STATUS and TIMING through the existing USB owner. It displays the MCU-reported full-board period/debounce interval and the separately measured USB SCAN round trip. Timing is unavailable until reported by the connected firmware; it is never replaced by a preset value. SCAN returns the firmware's latest debounced snapshot, not a guaranteed newly acquired frame. The board grid updates from sensor reports while the game continues; viewing the page does not reset or edit the game. It does not control LEDs, motors or the magnet.

Pages omit the team-name header, LOCAL UI badge and physical-board footer.

Manual execution remains the default. In computer mode, open **Computer move / instructions** and follow the real Stockfish move manually. Instructions describe removals, moving a second piece and replacing a pawn where required. Replacement acceptance requires both matching occupancy and explicit confirmation of the specified piece.

For a separately calibrated and hardware-verified mechanism, launch the service with `SCB_AUTOMATIC_MOTION=1` to expose **Execute automatically** for simple computer moves only. It requires a valid origin/steps declaration, then sends GOTO and MOVE through the existing MCU interface. Human moves are blocked until both DONE and a newly requested matching SNAPSHOT arrive. A mismatch, interruption or fault pauses the game without recording the computer move. No automatic capture, collision avoidance, CoreXY conversion or homing is supplied by this interface; these need separate hardware/motion integration. Tests use simulated actuators only.

Faults survive USB reconnection. Resolve the physical cause, then use **Board test → Reset fault**. The service checks safe idle outputs, a cleared MCU fault latch and fresh matching occupancy. Reset does not resume play; press **Resume** separately. It invalidates the carriage reference, which must be declared again before another automatic move. Firmware without SNAPSHOT/CLEAR_FAULT support cannot pass reset/resume verification.

The service sends `GUIDE` for all legal destination squares, `MARK ... LEGAL` for blue source/green destination and `MARK ... ILLEGAL` for red source/destination. Illegal feedback remains until accepted-position restoration. Turning guidance off does not clear an illegal warning. Preparation and game completion send LED_CLEAR; periodic scans do not clear accepted feedback. LED ACK means queued output, so the 500 ms physical illumination target still needs measurement on the assembled board.

## New game and Active Game

- **Two players:** two saved human players. The Pi validates physical moves.
- **Vs computer:** a saved human plays White or Black against the actual local Stockfish process. Searches run in a worker, while scanning, clocks, pause and navigation remain responsive. Default search time is 2 seconds; the existing engine wrapper enforces its response budget.
- **With coaching:** two saved humans with optional online AI advice from the existing OpenRouter coaching API. White and Black opt in independently before setup and can toggle their own setting during play. Only the enabled player to move triggers an AI request. The service sends a snapshot of the current FEN and legal moves; a returned suggestion must be legal and current. Advice never plays a move or falls back to Stockfish. The AI coaching page shows the full returned explanation and allows retry. Both OFF makes no API request and needs no key.
- **Guidance:** local legal-destination guidance and Stockfish Hint are available only in Two players mode. Vs computer has no Guidance or Hint controls; its Stockfish opponent still chooses computer moves. With coaching uses separate White/Black AI settings, not a global Guidance toggle.
- **Time control:** both clocks are maintained by the service using monotonic time, independent of the currently displayed page. They switch only after an accepted physical move.
- **Pause / Resume:** clocks stop; board sensing continues. Moves are not committed during pause. Resume requires reconnection and synchronization with the accepted position.
- **Board connection:** opens the same basic connection controls during a game. Reconnection keeps the game paused until the physical position matches and Resume is pressed.
- **End:** Cancel keeps the game. Confirmation records White win, Black win, Draw or End without a result, as selected by the players. Rules-detected checkmate/draw stores its actual result automatically.
- **Clock expiry:** pauses the game and asks the players to confirm the outcome; it does not invent a FIDE timeout result without complete material adjudication.
- **Hint / AI coaching:** Two players can request a local Stockfish hint. With coaching opens a dedicated online-advice page; Request/Retry is available only on an enabled, synchronized turn. Vs computer has neither control. Failed AI calls show an error and do not prevent human play.
- **Confirm move:** enter UCI, such as `e2e4`, when sensor changes are ambiguous. The same legality and matching-occupancy checks still apply. Promotions require a piece choice. Castling waits for the complete king/rook occupancy change.
- **View position:** opens the last recorded position without altering the live game, useful when restoring an illegal move. Back returns to Active Game. Clocks continue while viewing unless paused.

Board disconnect, stale sensor data or local UI-controller loss pauses an active game. Reconnection never silently resumes clocks or accepts an unverified position. An engine error does not fabricate a move. A failed SQLite move write does not advance the logical position.

## Board connection

Only the essential port selector and Connect/Disconnect button remain in **Set up the board**. **Check position** requests a full-board snapshot. Periodic snapshots keep game data fresh; disconnected or stale boards cannot start or silently resume a game.

Sensor events still update the game. Board test shares the same connection; close external serial terminals before connecting. Missing or malformed data is unavailable, not an empty board. Invalid data pauses an active game. Coordinates pass through unchanged from firmware; physical wiring-to-coordinate mapping still needs on-board verification.

## SQLite players and history

Default database:

```text
~/.local/share/scb/players.sqlite3
```

`XDG_DATA_HOME`, `SCB_PLAYER_DB`, or `--database PATH` can override it. It is outside the code directory and is not included in an update.

The shared `pi5/storage/schema.sql` migrates the earlier player-only schema in place to version 2. Existing player IDs, names and selection remain. Tables contain players, selection, board settings, games and accepted moves. Each move stores the resulting FEN and both clocks. Game rows retain participant-name snapshots even if a player is renamed/deleted later.

Players support creation, selection, rename, confirmed deletion and pagination. Counts are computed from actual completed game rows for the selected player ID: completed games, wins, losses and draws. Active/interrupted games are excluded; games ended without a result count as completed but not as wins/losses/draws. Renaming preserves statistics because the ID is unchanged. Names are 1-24 printable ASCII characters, trimmed and unique ignoring ASCII case. The bundled font lacks Chinese glyphs; unsupported names are rejected. SQL values are bound parameters. No player is created automatically.

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
| `../app/ui_game.py` | Legal physical moves, clocks, game state and independent Stockfish/AI workers |
| `../app/ui_coach.py` | Noninteractive adapter to the existing OpenRouter coaching transport |
| `../app/game_store.py` | Transactional game records and read-only replay |
| `../storage/schema.sql` | One database schema shared by C and Python |

The socket defaults to `$XDG_RUNTIME_DIR/scb-ui.sock`, or `~/.local/share/scb/scb-ui.sock`; override with `SCB_UI_SOCKET`. It is local and user-only. The service log is next to the database as `ui_service.log`. `SCB_SERIAL_PORT` can advertise an explicitly configured serial device. Never run a separate serial console against the same board while this service is connected.

## Verification

```sh
sh pi5/ui/setup.sh
```

Checks include native rules, USB framing, actual SQLite migration/persistence, legal move acceptance, clocks, pause/resume, checkmate, captures, castling, promotions, stale/disconnected boards, failed persistence and actual Stockfish opponent/hint searches. The native UI integration test goes through widgets, a Unix socket, the real rules/SQLite service and a PTY-emulated MCU, checks the diagnostic grid and TIMING response, toggles guidance, reconnects a paused game, then reopens saved replay. Additional tests cover ambiguous-move confirmation, computer replacement confirmation, discarded hint results, invalid occupancy, real completed-game statistics and failed resume writes. SDL tests cover mouse/touch fast clicks and keyboard controls at three window sizes.

Tests and screenshots use isolated temporary databases; they do not create fixtures in the user's player library. No test commands a physical motor, opens a real board or calls a network API. PTY timing/inputs are test fixtures, not measured hardware results.

The development Mac build passes these software checks. Pi ARM64 execution, actual sensor polarity/orientation, physical touch and end-to-end hardware latency require verification on the connected Pi and board.

`preview/index.html` is only an offline layout gallery, generated by the C renderer with an empty temporary database and no service. It contains no working database or sample games. The initial-board image is explicitly the target arrangement. Real operation requires the native launcher.

## References

- [SQLite C interface](https://www.sqlite.org/cintro.html)
- [SQLite JSON functions](https://www.sqlite.org/json1.html)
- [Official Touch Display 2 installation](https://www.raspberrypi.com/documentation/accessories/touch-display-2.html)
- [LVGL 9.3 SDL integration](https://lvgl.io/docs/open/9.3/details/integration/driver/sdl)

## Updating an existing Pi installation

Close the running SCB window, copy the updated source into the existing `SCB_Pi5` folder, then run:

```sh
cd ~/SCB_Pi5
sh pi5/ui/setup.sh
sh pi5/start.sh ui
```

Keep `~/.local/share/scb/players.sqlite3`; it contains your actual players and games. Do not copy a Mac build or virtual environment to the Pi. This update uses the existing schema and does not delete players or games. Online coaching requires Internet and a key saved on this Pi. Automatic motion and stretch features such as time bonuses are not enabled. Local Stockfish remains the offline PvC opponent.

## AI coaching setup on the Pi

A key saved on your Mac is not automatically copied to the Pi. If the Pi has no saved OpenRouter key, close the UI and run from the Pi Terminal:

```sh
cd ~/SCB_Pi5/pi5
.venv/bin/python app/play.py --set-api-key
```

Input is hidden. The existing private `pi5/.openrouter-key` file is reused and excluded from Git/update archives. `OPENROUTER_API_KEY` overrides that file; `OPENROUTER_MODEL` selects a model, otherwise the existing default applies. No key is written into game records, UI state or screenshots.

UI AI requests run in a separate worker, with an 8-second HTTP timeout, one attempt per request and a 10-second UI waiting limit. Failure shows an unavailable message without pausing human play or generating replacement advice. Old-position results and results disabled while pending are discarded. Changing networks may require retrying AI advice. Tests mock HTTP responses and do not charge an API account; real connectivity, credentials and model availability need verification on the Pi.

## Board / Sensor Test display rotation

The diagnostic board defaults to a PCB-oriented view with a1 at the top left. Tap `View: ... CW` above the grid to cycle 0 -> 90 -> 180 -> 270 degrees clockwise. Square positions, edge labels, tap selection, occupancy colors and mismatch borders move together. The choice is kept while this application is running; restarting restores the PCB-oriented default. This affects only the diagnostic display, not firmware coordinates, LED mapping, game setup, saved positions or replay. Rotating does not disconnect USB, scan, move a piece or alter the active game.
