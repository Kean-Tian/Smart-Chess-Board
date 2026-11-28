# Integrated LED diagnostics — TIDR #40 / #41

These pages extend the existing C/LVGL touchscreen and Python UiCore, with the existing ESP32 firmware unchanged. They are separate from `tests/tidr_demos/`; those standalone demos are unchanged. No new serial connection, UI client, chess engine, database schema or replay implementation is introduced.

## Build and launch on the final Pi

Close the existing application with **Quit Game** first. Do not kill/restart services or run a standalone serial demo concurrently. From the repository root on the Pi desktop:

```sh
sh pi5/ui/setup.sh
sh pi5/start.sh ui
```

`setup.sh` installs existing dependencies, builds the rules and native SDL2 UI, and runs software checks. It does not flash firmware or launch the board application. For an already provisioned Pi, rebuild without reinstalling dependencies:

```sh
sh pi5/ui/build.sh
sh pi5/start.sh ui
```

The launcher uses the existing database and one service/controller. Diagnostics themselves do not write records. Use `SCB_PLAYER_DB=/absolute/path/to/separate-test.sqlite3 sh pi5/start.sh ui` if you want an isolated player/game library; this can be a new database, and LED diagnostics need no players or games. Do not copy Mac binaries/virtual environments to the Pi. Use the Pi desktop, final ESP32-S3/Sensor PCB, final LED array and final touchscreen.

## Touchscreen-only operation

After installation/launch, no SSH, terminal or Python script is required for these demonstrations.

1. Open **Board test → Sensor Test**, select the existing port, and **Connect**. Wait for fresh occupancy. If fault recovery is needed, resolve the physical cause and use the existing **Reset fault** workflow. Outputs must report armed=0, moving=0 and magnet=0. Do not use LED diagnostics during a running or paused game; end it through its normal workflow first.
2. Back returns to **Board Test**. Open **LED Test**. The three entries are disabled when disconnected, during an active/paused game, on a latched fault, or while a previous clear still owns LEDs. The backend also rejects incompatible entry independently of these UI checks.
3. Back from an LED page cancels unsent commands and clears the array. While connected, the page normally waits for the clear ACK before returning. Check the physical array is dark. A clear ACK confirms a queued MCU operation, not optical darkness.

### Mapping and independent LEDs — #40

Before full-array tests, open **Manual LED Test**. Choose **Red**, tap a1, then test h1, a8 and h8 one at a time with **Clear All LEDs** between checks. Confirm each label addresses the actual corresponding final-board square; also check interior e4 and every remaining square. Record any discrepancy as FAIL/BLOCKED and stop using the mapping until investigated. Do not compensate by changing firmware or swapping coordinates during the checkoff.

The LED grid uses the same logical orientation as the game/review board: a8 upper-left, h8 upper-right, a1 lower-left, h1 lower-right. Commands use logical square names unchanged (`a1` = bit/index 0); the existing firmware handles the physical serpentine strip and configured reversal flags. The existing Sensor Test has its own PCB display correction and remains unchanged; do not infer LED coordinates from that corrected sensor view. Actual wiring mapping still requires the physical checks above.

Then demonstrate independent control:

1. Red → a1; Green → e4; Blue → h8. Observe all three physical LEDs simultaneously.
2. Off → e4. Observe a1 red and h8 blue remain unchanged. The acknowledged active count should change from three to two.
3. White → an individual square; verify actual white output. Clear All LEDs, verify darkness, then Back.

UI colors and active counts describe acknowledged commands. Unknown data is gray. They never certify actual light or colors. A pending tap may briefly precede its ACK; the selected color control is local, and an acknowledged command reports the last applied square.

### Sequential RGB — #40

1. Open **Automatic RGB Test**, wait for entry clearing, press **Start**.
2. Observe a1 red → green → blue → off, then b1, through h8. At most one LED is commanded on at a time. Color dwell is approximately 200 ms **after each ACK**, plus service scheduling/USB latency; it is not a measured optical duration.
3. **Pause** prevents subsequent colors; an already-dispatched request may finish. **Resume** continues; **Restart** drains the old request, clears, and begins again at a1. **Stop** drains and clears without leaving the page. Demonstrate each control.
4. Allow the sequence to finish at 64/64. Independently check every physical square/color using direct observation or video. Completion is not an automatic hardware PASS.
5. Press Back, wait for clear confirmation and verify darkness. Return to Sensor Test and verify its existing occupancy behavior. Run the normal game regression demonstration separately when required.

Record: hardware/firmware revision, square/color observations, video filename, mapping checks, control/cleanup results, operator and TA/date. Mark #40 PASS only from final-hardware evidence; software tests and ACKs alone are insufficient.

### Current load and transitions — #41

The electrical team explicitly confirmed that all 64 LEDs with RGB channels each <=32/255 may safely run continuously. The diagnostic commands stay inside that envelope. `SCB_LED_CHANNEL_LIMIT` is currently 32 in `esp32/main/board_pins.h`; it is a channel cap, **not a measured aggregate-current limiter**. There is no current telemetry interface. The UI always states **Current: NOT MEASURED** and produces no automatic PASS.

1. With appropriate external current measurement equipment installed by the electrical team, open **Current Limit Test**. Measure the LED-array supply branch, not an unrelated Pi/whole-system supply. Use a calibrated time-resolved current probe/logger or shunt/scope with appropriate range, bandwidth and documented uncertainty; a slow single-number multimeter reading cannot establish every sliding one-second average.
2. Begin recording before selecting a pattern. Exercise **Max Load**, **All Red**, **All Green**, **All Blue**, **All White**, **Transitions**, **Clear All LEDs** and **Stop Test**. Max Load and All White both command (32,32,32) on all 64 squares. Patterns are applied through 64 existing per-square LED commands; intermediate states and load ramps must remain in the recording. Transitions cycle red/green/blue/white, holding about one second after the full pattern is acknowledged. These are test stimuli, not a new current-control algorithm.
3. Record startup, each pattern, steady state, every color transition, clear/stop and exit. Keep enough pre/post data to evaluate complete one-second windows. Export raw time/current samples and compute the time integral of current over **each sliding one-second window**, divided by 1 s. For irregular samples use timestamps and integration, not an unweighted sample average.
4. Acceptance: average LED-array current <=2.0 A over any one-second interval. Record maximum observed rolling average, instrument uncertainty, sampling settings, trace filenames and coverage. Missing time-resolved measurement is BLOCKED. Exceeding the limit is FAIL. Passing sampled patterns alone is not proof of *all* permitted production states/transitions; document additional coverage needed for that claim. No firmware limiter was added or inferred.
5. Stop, verify all LEDs off, Back and confirm clear. Elapsed time is backend monotonic diagnostic runtime, including application of the pattern, not an instrument timestamp or current measurement.

### Disconnect, recovery and exit

During an operator-authorized diagnostic, unplug the existing USB link. The sequence must stop and unsent work be discarded. The UI reports unknown physical LED state; it must not claim a successful clear. Back may leave an errored/disconnected page so Sensor Test remains accessible; backend LED ownership still blocks gameplay. Reconnect through Sensor Test. The backend checks idle outputs and sends a final clear on the new link before releasing diagnostic ownership; it never automatically resumes a sequence. Resolve/reset any latched fault using the normal workflow, then explicitly reopen the desired test.

On **Quit Game** or normal service shutdown the existing lifecycle cancels diagnostics and attempts a final bounded clear. If disconnected/unacknowledged, check the actual array and isolate LED power safely as appropriate; a disconnected controller cannot guarantee darkness. Abrupt power loss/process termination cannot guarantee cleanup.

## Architecture and isolation

- `LedDiagnostics` is a cooperative state machine advanced by the existing service update loop. It shares `UiCore.led_io` and `UiCore.link`; it creates no dedicated thread, second connection or periodic UI callback.
- Entry rejects active/paused games, motion/stopping and faults, then checks MCU STATUS before issuing LEDs. Normal feedback already in flight drains first. While diagnostics own LEDs, `feedback_update` submits no normal feedback. Gameplay prepare/start/resume/commit/automatic execution are rejected until diagnostic clear releases ownership.
- Diagnostic requests bypass clock ticks and never call GameSession mutators or GameStore writes. Existing background sensing remains active; the new pages do not create game records. Normal game/rules/clock/transaction algorithms are unchanged.
- One bounded LED request can be in flight. Cancel increments a generation token, clears unsent tasks and cancels a queued future. A request that already reached the MCU can finish; stale completions cannot restart work. Ownership stays held until its final clear is acknowledged. Manual taps coalesce per square (at most 64 unsent commands).
- New requests use only STATUS, LED and LED_CLEAR. No diagnostic command arms, homes, moves or activates the magnet. Existing fault/shutdown safety handling is preserved.
- ACKs do not establish optical output, current or compliance. All display states use this distinction.

## Files in this change

| File | Reason |
| --- | --- |
| `pi5/app/led_diagnostics.py` (new) | Exclusive LED state machine, RGB sequence/manual/load, cancellation and cleanup |
| `pi5/app/ui_service.py` | Integrate diagnostic command namespace/state into existing ownership/executor/lifecycle |
| `pi5/ui/src/led_test_ui.inc` (new) | Separate native LED page widgets using existing shell/bridge/style |
| `pi5/ui/src/scb_ui.c` | Board Test navigation, actions, state refresh, exit handling and native regression exercises |
| `pi5/ui/src/scb_ui.h` | Append page IDs without renumbering existing pages |
| `pi5/ui/src/main.c` | Update pointer-test expected Board Test landing-page title only |
| `pi5/tests/led_diagnostics_tests.py` (new) | Isolated software tests for sequencing, caps, ownership and cleanup |
| `pi5/CMakeLists.txt` | Register the diagnostic software test suite |
| `pi5/ui/README.md` | Correct navigation references and link this procedure |
| `pi5/ui/LED_DIAGNOSTICS.md` (new) | Build, operation, evidence, limitations, verification and scoped rollback |

Firmware, schemas, game rules/clock/store implementations, serial protocol/driver, old standalone demos and production database files are unchanged.

## Revert only this feature

Do not run a repository-wide reset/restore. Before changing anything else, preserve a scoped patch for the six modified existing files (the working tree was clean before this task):

```sh
git diff -- pi5/CMakeLists.txt pi5/app/ui_service.py pi5/ui/src/scb_ui.c pi5/ui/src/scb_ui.h pi5/ui/src/main.c pi5/ui/README.md > /tmp/scb-led-diagnostics-existing.patch
```

Review it. If it contains only this feature, `git apply --reverse --check /tmp/scb-led-diagnostics-existing.patch` checks reversibility; `git apply --reverse /tmp/scb-led-diagnostics-existing.patch` reverses those exact edits. Separately archive/remove **only** the four new files listed above after checking they have no later work: led_diagnostics.py, led_diagnostics_tests.py, led_test_ui.inc and this document. If changes were committed or subsequently edited, use a reviewed feature-only commit revert or a freshly reviewed scoped patch instead. Rebuild the UI afterward. No database rollback/migration and no firmware flashing is needed.

## Executed software verification — 2026-11-27

- Root CMake build (`build/mode-selection`) succeeded; **16/16 CTest groups passed**. These include chess rules, legal/illegal moves/restoration, guidance/accepted/illegal LEDs, clocks, state/storage, computer/coaching behavior, USB framing, PCB mapping and portable MCU/motor logic.
- Dedicated `led_diagnostics_tests.py`: **14/14 tests passed**, covering all 256 sequential RGB/off commands, single-LED exclusivity, manual independence/coalescing, all capped load patterns, pause/resume/restart/stop, pending/in-flight cancellation, ownership, disconnection/reconnection, shutdown and no diagnostic database writes/clock ticks. The shutdown test explicitly drains pre-existing normal feedback before the final clear.
- Headless native LVGL build (`build/led-diagnostics-ui`, `-Wall -Wextra -Werror`) succeeded; **3/3 CTest groups passed**, including player SQLite, all native page/widget/bounds interactions and the UI → Unix socket → real rules/SQLite → PTY-emulated MCU integration. The integration exercises diagnostic manual selection, automatic controls, 64-pixel load and acknowledged page exit, in addition to the existing gameplay/sensor/replay regression.
- Native snapshots were rendered and the three new diagnostic-page layouts were visually inspected. These are offline layout previews, not final touchscreen measurements.
- `git diff --check` passed. Six existing files are modified and four new files added, all enumerated above. No ESP32 source, schemas, old standalone demo, protocol/serial driver, game rules/clock/store code or production database was changed.

Initial native integration attempts failed because pyserial was absent and the local sandbox denied Unix-socket bind. Pyserial was installed into a build-only virtual environment; the software integration test then passed outside the socket-restricted sandbox with temporary SQLite/PTY fixtures. No real board/service was launched. The root test group's optional native integration case is skipped when no UI binary is supplied; the separate native CTest run above explicitly supplied it and executed it.

Not executed: SDL2 mouse/touch input test (SDL2 development dependency unavailable on this Mac; headless build excludes it), Pi ARM64 execution, physical touchscreen use, actual optical sequencing/mapping and current measurement. The Pi `setup.sh`/native build runs the SDL2 input test. Hardware #40 remains NOT RUN; #41 measurement remains BLOCKED until external time-resolved evidence is collected. No hardware PASS is reported.

Local software reproduction (from repo root; the build-only environment requires pyserial):

```sh
cmake -S . -B build/mode-selection
cmake --build build/mode-selection -j 4
ctest --test-dir build/mode-selection --output-on-failure
cmake -S pi5/ui -B build/led-diagnostics-ui -DSCB_UI_HEADLESS=ON -DPython3_EXECUTABLE="$PWD/build/led-check-venv/bin/python"
cmake --build build/led-diagnostics-ui -j 4
# Mac rules-library suffix; use .so for a Linux build.
SCB_RULES_LIBRARY="$PWD/build/mode-selection/lib/libscb_rules.dylib" ctest --test-dir build/led-diagnostics-ui --output-on-failure
```

The build-only virtual environment used here was prepared with `python3 -m venv build/led-check-venv` and `build/led-check-venv/bin/pip install 'pyserial>=3.5,<4'`. On a provisioned Pi, the existing setup environment is sufficient. Unix-socket/PTY permissions are needed for software integration; no physical device permissions are required for those tests.
