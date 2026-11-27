# Team 24 standalone TIDR #19 and #33 demonstrations

These scripts reuse the original `ui_service.Server`, `UiCore`, `GameSession`,
`GameStore`, native rules library and native touchscreen UI. They never flash
firmware, edit production files, open a second serial connection, or stop/restart
normal services. All game records are in fresh, designated demo databases.

**No final-hardware result is supplied with this framework.** PASS requires real
application traces and operator-reviewed physical evidence. An attachment is an
operator assertion, not automatic verification of a video's contents. Review the
recording with the TA. Missing evidence produces BLOCKED; observed violations
produce FAIL. Software checks are not hardware checkoffs.

## Prerequisites and ownership

- Use the final Raspberry Pi 5, final touchscreen and final PCB/sensors/pieces.
  Existing Pi environment, native UI and rules library must already be installed.
  The scripts never invoke setup/build/install commands.
- Use the Pi desktop session. `fuser` must be available for read-only device-owner
  checks. Uninspectable ownership blocks service launch. Check the output yourself:
  process-name checks cannot identify every possible controller or another user's
  devices. Do not launch from a terminal inaccessible to the GUI.
- Exit the normal application through its UI **yourself**; close serial terminals
  and other controllers. Do not launch demonstrations alongside it. Keep motor
  output disabled; automatic motion is off in the demo service.
- Use explicit paths in the commands below. Replace `/dev/ttyACM0` with the final
  board's actual device. USB alone does not power the final master PCB.
- Do not set `SCB_PLAYER_DB` globally. The launcher refuses configured/default
  production DB aliases, symlinks and hard-linked databases. A run must be a direct
  child of `tests/tidr_demos/runs/`, initially created by `preflight --init`.

All commands below start from the repository root. In each terminal define:

```sh
TASK_ROOT="$PWD"
DEMO="$TASK_ROOT/tests/tidr_demos"
PY="$TASK_ROOT/pi5/.venv/bin/python"
RECORDS="$DEMO/runs/records-19-33"
FAILURE="$DEMO/runs/failure-19"
```

## Launch an isolated real application (manual only)

```sh
"$PY" -B "$DEMO/preflight.py" --init "$RECORDS" --purpose records --port /dev/ttyACM0
"$PY" -B "$DEMO/run_demo_service.py" --run "$RECORDS" --port /dev/ttyACM0 --operator-confirms-controller-stopped
```

`--init` creates metadata only: no DB, UI, service, socket connection or serial
connection. An existing run name is rejected. Missing hardware/software may cause
preflight exit 2 after creation; fix prerequisites and use `--run "$RECORDS"`
instead of initializing again.

The foreground service prints an **exact native UI command** containing its private
`SCB_UI_SOCKET` and `--database` paths. Paste that command into a second desktop
terminal. It launches the existing `pi5/ui/build/native/scb_touch_ui` directly,
avoiding a second launcher/service. Do not run `pi5/start.sh ui` alongside it.
Select the real port and press Connect board in this native UI. The service alone
opens the port through production `ScbLink.open(..., exclusive=True)`.

The observer timestamps the original functions using call/return profiling; it
does not replace code, clocks, responses or decisions. It records serial command
attempts at the original `_write` boundary (including heartbeat/STOP), real replies,
game state, History/Review replies and committed read-only database snapshots.
Observation errors block verification. Timing includes observation overhead.

To finish: End active demo games normally when appropriate, Quit the UI, then
Ctrl-C in **this demo service's terminal**. Production cleanup closes its own
serial link and sends STOP (which invalidates carriage origin). No normal service
is touched. If LEDs remain on after interruption, manually relaunch this isolated
app, connect and use normal game preparation/end controls to clear them. A closed
port does not prove safe physical outputs: verify motor/magnet off and LEDs clear
with the TA. On lost communication, verify safety manually; do not reset faults
or reconnect a second owner automatically. Restore physical pieces manually.

The launcher constructs the existing `ui_service.Server`, invokes its original
`run()` loop and `close()` cleanup, and handles signals only for this demo process.
After the loop stops it attempts LED_CLEAR, STOP and safe-output STATUS through
the same owned link before closing it. It never clears fault latches. Missing
acknowledgments are reported; LED ACK does not prove physical darkness.

## Generate a completed test game without physical play

From the repository root, generate a fresh isolated fixture database with one
command (use `python3` if the existing Pi virtual environment is unavailable on a
development host with the native rules library):

```sh
pi5/.venv/bin/python -B tests/tidr_demos/generate_test_game.py --init --run "$PWD/tests/tidr_demos/runs/replay-fixtures" --operator-confirms-demo-closed
```

This does **not** launch a UI, service or hardware test. Close any application
using **this test database** first. It validates `f2f3 e7e5 g2g4 d8h4` with the
production native rules, creates/reuses `TIDR Fixture White` and
`TIDR Fixture Black`, then calls original `GameStore.start()` and `move()` APIs.
The native rules determine checkmate and result `0-1`; every position is calculated
by those rules. The fixture uses PvP/no-clock metadata and visibly labels its
stored reason `GENERATED TEST FIXTURE - no physical gameplay`. Both player IDs
are actual saved test profiles, not invented foreign keys.

`GameStore` has **no Python player-creation API**. Automatic profile creation uses
the existing public native `player_store_open/page/create/selected/close` APIs
through `common/fixture_players.c`, a thin adapter with no SQL. The script compiles
that adapter together with unchanged production `player_store.c`, using the
unchanged shared schema as a generated build include. All build artifacts remain
under the test run. This requires an installed `cc` compiler and SQLite development
headers/library; no packages are installed. Missing prerequisites report BLOCKED.
Alternatively, create profiles in the native UI using this same test DB, close
that UI/service, and pass `--white-id N --black-id M` to skip the helper build.

To add another complete game without overwriting records, omit `--init`:

```sh
pi5/.venv/bin/python -B tests/tidr_demos/generate_test_game.py --run "$PWD/tests/tidr_demos/runs/replay-fixtures" --operator-confirms-demo-closed
```

Every invocation appends a new game ID, reuses the named fixture profiles, and
checks that all earlier game/move records remain exact. Active/paused test games
block generation. Failures retain records and an incomplete-attempt marker rather
than deleting anything. `generated_games.jsonl` records fixture provenance and
verification, separately from physical event evidence. The generator reopens the
DB and verifies `GameStore.history()` and `review()` for the initial position and
all four plies. Exit 0 means **fixture data verified**, not a TIDR hardware PASS.

**Simple TA procedure for the generated Game Log record:**

1. Run the generator and note its printed game ID and test DB path. Show the TA
   the fixture label and `0-1` result; explain that no sensors produced this game.
2. On the final Pi desktop, safely close the normal controller yourself. Launch:

   ```sh
   pi5/.venv/bin/python -B tests/tidr_demos/run_demo_service.py --run "$PWD/tests/tidr_demos/runs/replay-fixtures" --port /dev/ttyACM0 --operator-confirms-controller-stopped
   ```

3. Paste the service's printed native UI command in a second desktop terminal.
   It explicitly selects `runs/replay-fixtures/players.sqlite3` and the private
   socket. Do not open the normal production DB. Open **History**, select the
   generated game, show players/result, then Next through four moves and Previous
   back to the initial position. Saved review itself needs no board connection.
4. For the **full #33** preservation/no-movement-command demonstration, follow the
   #33 procedure below using this generated saved game ID. Start and pause a
   separate current game on the final physical board; that does not require
   physically playing the saved four-move game. Retain final-touchscreen video
   and real command-stream evidence. Merely generating a DB does not pass #33.
5. Quit the demo UI and Ctrl-C its service normally. Leave the records intact.

For **#19**, generated data can prepare storage, restart and power-cycle tests,
but it supplies no measured real-application completion, sensor pipeline or
failed-write evidence. The complete #19 procedure below must still be performed
independently with the appropriate actually observed game ID. The #19 evaluator
does not accept fixture generation as a timed `GameSession` completion.

**Example only, not a hardware result:**

```text
FIXTURE VERIFIED (software/data only): game ID 1; Black wins 0-1; 4 legal plies
Verified initial position and every move/position via production history()/review(), including reopen.
NOT a sensor-to-gameplay or complete TIDR #19 hardware PASS.
```

## #19 sequential TA checkoff

1. Start the isolated records application as above. Through **Players**, create
   `TIDR White` and `TIDR Black`. Start Two players, no clock, guidance off. Set up
   the actual standard board, Check position, confirm types/colors, Start.
2. Physically play `f2f3 e7e5 g2g4 d8h4`. Show each accepted move and the actual
   checkmate. Record the assigned game ID from the trace/database (fresh runs
   normally begin at ID 1; never assume it). A separate manually ended game can
   also be measured with its actual sequence/result.
3. Quit UI, Ctrl-C demo service. The completion observation spans entry to the
   completion operation through a **separate read-only connection's availability**
   of the committed record. Entry precedes completion determination, so ≤2000 ms
   is a conservative upper bound. Writer `synchronous`/journal settings are
   observed without changing them. Separate-reader visibility alone does not
   establish storage-media survival; the power-cycle step is mandatory.
4. Manually launch the same service command again using `--run "$RECORDS"`, and
   paste its native UI command again. Open History and confirm exact saved details,
   all four moves and positions. Quit UI/Ctrl-C service. The next service startup
   snapshots the same DB; no script restarts it for you.
5. Record the physical setup/play and save the video/photo outside the source
   tree or in a suitable evidence location. Attach it (use your actual file):

   ```sh
   "$PY" -B "$DEMO/record_evidence.py" --run "$RECORDS" --kind hardware --label setup --file /path/to/actual-checkoff-video.mp4 --operator 'Your name' --note 'Final Pi 5, final touchscreen and PCB; physical four-move game, ID 1; TA observed'
   ```

6. Run a **separate** failure fixture after the records service is safely closed:

   ```sh
   "$PY" -B "$DEMO/preflight.py" --init "$FAILURE" --purpose failure --port /dev/ttyACM0
   "$PY" -B "$DEMO/run_demo_service.py" --run "$FAILURE" --port /dev/ttyACM0 --operator-confirms-controller-stopped
   ```

   Paste its printed UI command. Create profiles and start a real standard-board
   PvP game. Pause it. In a third terminal:

   ```sh
   "$PY" -B "$DEMO/demo_19_record_persistence.py" arm-failure --run "$FAILURE" --confirm-isolated-test-db
   ```

   Resume in the native UI and physically play e2e4. The named test-only SQLite
   trigger aborts the original position UPDATE after the original move INSERT.
   Show “Move was not saved,” paused/restoration state, unchanged accepted
   position/history and no committed partial move. This is a real SQLite failure,
   not a fake store response. Do not reset the production controller.

   Quit UI and Ctrl-C this failure service; then:

   ```sh
   "$PY" -B "$DEMO/demo_19_record_persistence.py" disarm-failure --run "$FAILURE" --confirm-isolated-test-db
   "$PY" -B "$DEMO/record_evidence.py" --run "$FAILURE" --kind hardware --label failed-write --file /path/to/actual-failure-video.mp4 --operator 'Your name' --note 'Final hardware; real e2e4 rejected after isolated SQLite ABORT; accepted state unchanged'
   ```

   Disarming drops only the fixture trigger, retaining all test records. Do not
   manually remove moves or alter game rows to make a result pass.
7. **Normal power-cycle procedure:** with demo UI/service closed, use the Pi's
   normal OS shutdown, wait for shutdown, switch intended system power off/on,
   boot and manually launch the records service/UI again. Do not pull power while
   Linux runs. In History verify the designated game. Quit UI/Ctrl-C service.
   Attach actual evidence and notes describing shutdown/power cycle, not just reboot:

   ```sh
   "$PY" -B "$DEMO/record_evidence.py" --run "$RECORDS" --kind power-cycle --label 1 --file /path/to/actual-power-cycle-video.mp4 --operator 'Your name' --note 'Game 1 verified after normal shutdown, system power off/on and manual relaunch'
   "$PY" -B "$DEMO/demo_19_record_persistence.py" evaluate --run "$RECORDS" --game-id 1 --expected-moves 'f2f3 e7e5 g2g4 d8h4' --white 'TIDR White' --black 'TIDR Black' --result 0-1 --failure-run "$FAILURE"
   ```

   Change IDs/sequence/names/result to exactly what you actually used. Evaluation
   requires a later service startup with a different Linux boot ID and exact
   record preservation, plus the operator's power-cycle evidence. Application
   restart alone cannot pass #19. A simulated or software-only run remains BLOCKED.

## #33 sequential TA checkoff

1. Use the completed test game in the records DB above, or a generated fixture
   in its own `replay-fixtures` run. Set `RECORDS` to the run actually used and
   replace saved game ID 1 below with the generator's printed ID as necessary.
   With all other controllers closed, manually launch that service/UI again.
2. Start **another** physical PvP game, accept at least one move and pause through
   the UI. Leave its physical position fixed. While the UI/service are running:

   ```sh
   "$PY" -B "$DEMO/demo_33_game_log.py" begin --run "$RECORDS" --window replay1 --saved-game-id 1
   ```

3. In the **existing touchscreen UI**, return Home, open History and select saved
   game 1. Show its players/result/details. Show initial position, press Next once
   per move through the final position, then Previous once per move to the initial
   position. Keep video rolling over the whole sequence. Do not confirm moves or
   touch physical pieces. This records original `GameStore.history()/review()`
   results; the fixture supplies no replay engine/UI.
4. Return to Open current game. Show the other game's accepted position, history,
   pause status and remaining clocks unchanged. While it is still paused:

   ```sh
   "$PY" -B "$DEMO/demo_33_game_log.py" end --run "$RECORDS" --window replay1
   ```

   The begin/end commands only read observations/DB and append markers; they do
   not send socket or serial commands. If History is inaccessible during an active
   game, preserve the evidence and report BLOCKED; do not substitute scripted
   `GameStore.review()` calls as native UI proof.
5. Finish the active demo game normally, Quit UI and Ctrl-C demo service. Attach
   the actual video; then evaluate:

   ```sh
   "$PY" -B "$DEMO/record_evidence.py" --run "$RECORDS" --kind replay-visible --label replay1 --file /path/to/actual-replay-video.mp4 --operator 'Your name' --note 'Final touchscreen; saved game 1 details, every Next/Previous step, current paused game preserved, mechanism observed stationary'
   "$PY" -B "$DEMO/demo_33_game_log.py" evaluate --run "$RECORDS" --window replay1
   ```

   Serial coverage must contain live PING/replies, not an empty command list. Any
   attempted actuator command during replay fails the command assertion. No
   movement and no movement commands are separate observations. Native service
   replies cannot by themselves prove visible touchscreen rendering.

## Outputs, limitations and local software validation

Results are retained as `result-19-<timestamp>.json` / `result-33-<timestamp>.json`;
raw observations are `events.jsonl`, manual markers and hashed evidence attachments.
SQLite records/sidecars and previous reports are never purged. Exit codes: 0 PASS,
1 FAIL, 2 BLOCKED, 130 interrupted. Unexpected I/O/observation gaps block verification.

**Example only — not an executed hardware result:**

```text
TIDR #19: BLOCKED
  PASS: completion-to-committed availability <= 2000 ms — ... 18.412 ms ...
  BLOCKED: normal final-Pi power cycle preserves records — requires changed Linux boot ID ...
TIDR #33: BLOCKED
  PASS: no movement commands attempted during replay — observed 24 serial requests ...
  BLOCKED: native touchscreen visibly showed details and each step — operator video/notes ...
```

The scripts cannot independently authenticate operator recordings, physical piece
identity, safety, power removal or display contents. The TA must review those
artifacts. Do not attach fake files or PTY traces as physical proof. Observations
are not tamper-proof certification. No numeric deadline is invented for #33.

Local framework checks (no service/UI/serial launch, no hardware checkoff):

```sh
python3 -B -m unittest discover -s tests/tidr_demos/selftests -v
git diff --exit-code
git diff --cached --exit-code
git status --short --untracked-files=all
```

Selftests use only fresh fixture DBs and the existing native rules library when
available. Their synthetic board input is explicitly software validation and
cannot produce a completed physical checkoff. Missing native prerequisites skip
the relevant integration test. Existing production files must have no diff; all
new source files belong under `tests/tidr_demos/`.
