# Team 24 — final-hardware TA checkoff guide

Scope: **#19, #20, #22, #23, #27, #28, #33, #37, #38, #39**. This guide consolidates
the existing implementations; it does not certify hardware. **Every hardware test
is NOT RUN until the operator performs it.** No production or earlier demo file
was changed during consolidation. Start with the readiness checklist, then work
through the run cards in order. Do not paste all commands as an unattended batch.

### Run order at a glance

| Order | Run card / action | TIDRs | Service/connection handling |
|---|---|---|---|
| 1 | Preflight and all-64 mapping | Readiness for #37–39; occupancy readiness for all | All controllers closed; mapping releases its exclusive link |
| 2 | A: guidance, first two accepted moves, End/preparation | #23, #37, #38 | Start one unified main service; keep it running |
| 3 | B: rejection, unrelated action, partial/full restoration, legal move | #22, #39, #27 error | Same service; new No-clock game |
| 4 | C: three ambiguity cases | #20 | Same service; three fresh No-clock games |
| 5 | D: display overview and full clock workflow | #27 overview, #28 | Same service; one five-minute game; the required physical disconnect happens here only |
| 6 | E: legal check; F: actual four-move mate | #27 check/mate, #19 completion | Same service; new games; save actual completed game ID |
| 7 | G: saved replay with another current game paused | #33 | Same service; no disconnection/reset inside replay |
| 8 | Isolated real write failure | #19 atomicity | Close main safely; launch/close separate failure DB service |
| 9 | Return to main, then normal power cycle and main relaunch | #19 restart/persistence | Necessary manual restarts only; no extra main restart needed |
| 10 | Review/import physical evidence and evaluate | All 10 independent results | All demo services closed; no hardware/control access |

Mapping and LED windows must be captured in the same boot before the later #19
power cycle. Do not append a different post-reboot mapping to this run before
evaluating its earlier LED windows; current mapping records use monotonic ordering.

## 1. Readiness checklist and minimum preparation

Record identities, observations and instrument details in a copy of
`TA_CHECKOFF_RESULTS_TEMPLATE.md` under your test run.

| Check | Required preparation / verification |
|---|---|
| Final Raspberry Pi 5 | Final 64-bit Pi OS desktop, stable intended power, accessible terminal and storage. Copy the **whole repository**, including `tests/tidr_demos`, onto the Pi. A `pi5/`-only deployment is insufficient. |
| Python/software | Existing `pi5/.venv/bin/python`, Python 3.10+, pyserial 3.5–<4, SQLite support, native ARM64 rules library and native UI already installed. Do not run installers/build scripts during checkoff. |
| Native binaries | Expected UI: `pi5/ui/build/native/scb_touch_ui`. Rules resolve to `pi5/build/lib/libscb_rules.so` or `build/lib/libscb_rules.so`, unless an already-correct explicit override exists. A Mac dylib/build is not Pi evidence. `file PATH` can inspect architecture without running it. |
| ESP32-S3 / sensor PCB | Final master PCB and sensor board, intended external supply, straight/correct cable, stable magnets and known firmware capabilities: STATUS/fault reporting, SNAPSHOT, CLEAR_FAULT, GUIDE/MARK/LED_CLEAR. Unsupported deployed firmware is BLOCKED; this workflow never flashes it. |
| Occupancy / coordinates | Run the all-64 mapping capture below: empty board → each labelled square alone → empty again. Require the correct single firmware bit for every physical label. Do not infer physical orientation from the UI diagnostic rotation or patch masks to pass. |
| Final 8×8 WS2812B array | Same capture verifies exactly one correct physical LED, correct blue, and no extras at every coordinate. Inspect power/wiring; the capture does not adjust them. |
| Touchscreen | Final touchscreen actually displays the native UI; touch Players/New game/Back and verify responsiveness. Preview images, headless rendering and SDL dummy video are not physical proof. |
| USB/UART | Use the currently configured application transport. Native J5 USB commonly appears as `/dev/ttyACM0`; USB does not power the PCB. Optional J6 UART1 is 3.3 V, 115200 8N1 on GPIO17/18. Do not change firmware transport or use a second terminal against the device. |
| Pieces | Complete final magnetic chess set; verify physical types/colors manually. Hall occupancy alone cannot identify them. Keep the board accessible for simultaneous pawn lifts and partial restoration. |
| Isolated records | Initialize runs **on this Pi**, at their final paths and with the same user throughout. Manifests use absolute DB/socket paths and a UID-derived socket; copying Mac run folders unchanged will not work. Never select the production DB. |
| Storage | Reserve space for event logs, SQLite sidecars and video copies. Each evidence attachment copies the entire file; reusing one large recording for many labels multiplies storage. Prefer appropriately documented short clips and preserve calibration/frame references. |
| Timing equipment | Actual final-screen/full-array video or equivalent optical instrument, calibrated to Pi monotonic time with measured uncertainty. Photodetector onset measurement also needs full-array/color evidence. Without adequate equipment, #27/#37/#38 timing stays BLOCKED. |
| Safe ownership | Operator exits the normal app and all serial terminals first. No automatic killing, restarting or disconnecting other owners. Motor/magnet motion stays disabled; no ARM/GOTO/MOVE/JOG/MAGNET commands are part of the procedure. |

No C compiler is needed for the primary workflow: create profiles in the native
UI and physically play the four-move saved game. The optional generator's automatic
profile creation additionally needs an installed compiler and SQLite development
headers. Generated records are fixtures, never physical #19 completion evidence.

## 2. Terminals, paths and session rules

Use **T1** for the foreground service, **T2** for the native UI command it prints,
and **T3** for manual markers/evidence commands. Start each terminal in the same
repository root and define these variables (change the run names if already used):

```sh
TASK_ROOT="$PWD"
DEMO="$TASK_ROOT/tests/tidr_demos"
PY="$TASK_ROOT/pi5/.venv/bin/python"
RUN="$DEMO/runs/ta-checkoff"
FAILURE="$DEMO/runs/ta-checkoff-failure"
PORT=/dev/ttyACM0
WHITE='TIDR White'
BLACK='TIDR Black'
OPERATOR='Replace with your name'
```

Keep the real desktop DISPLAY/WAYLAND environment. In **demo terminals only**,
remove stale test/transport overrides; this edits no persistent configuration:

```sh
unset SCB_UI_TEST_MODE SDL_VIDEODRIVER SCB_PLAYER_DB SCB_SERIAL_PORT SCB_UI_SOCKET SCB_AUTOMATIC_MOTION
```

`SCB_UI_TEST_MODE=0` is still an enabled test mode because production tests for
presence, not truthiness. It must be **unset**. Do not use `--smoke-test`,
`--service-test`, preview mode or fake sensor input as checkoff evidence.

With all controllers safely closed, initialize both metadata directories:

```sh
"$PY" -B "$DEMO/preflight.py" --init "$RUN" --purpose records --port "$PORT"
"$PY" -B "$DEMO/preflight.py" --init "$FAILURE" --purpose failure --port "$PORT"
```

Inspect output and stop on BLOCKED. `--init` creates metadata but does not launch
hardware or a DB. If prerequisites fail after creation, fix the authorized setup
outside checkoff and use `--run "$RUN"` rather than repeating `--init`. Never
delete an existing run to reuse its name. Use `-B` consistently.

After successful initialization, create the operator's blank results copy without
overwriting any earlier signed/filled file:

```sh
cp -n "$DEMO/TA_CHECKOFF_RESULTS_TEMPLATE.md" "$RUN/TA_CHECKOFF_RESULTS.md"
```

### Observer selection

The new optional `run_ta_service.py` reuses the shared launcher's original service,
preflight, locks, explicit DB/socket, motion-disable environment and cleanup. Its
observer preserves the legacy #19 call/return records **and** existing mv/dc/LED
formats. It adds no game/control logic and no client connection.

**This consolidation phase performed static review only: the new launcher has
not been runtime-tested.** On operator launch, inspect for `observer_error` before
accepting results. The existing-launcher fallback is in Section 10. No test or
service was executed to prepare this guide.

Normal game setup, abbreviated **S** below: Back → Home → New game → Two players;
choose the two named profiles, explicitly choose No clock or 5 min as specified,
and Guidance setting. Set up the actual standard board, Connect if needed,
Check position, confirm physical types/colors, then Start. Between games use
native **End**, choose the truthful outcome (End without result is fine for
fixtures), then restore pieces manually. Do not confuse **End** with top-left
**Quit Game**, which exits the entire UI.

## 3. Mapping first — no UI/service may own the device

In T1, after preflight and before starting any service:

```sh
"$PY" -B "$DEMO/verify_led_mapping.py" --run "$RUN" --port "$PORT" --operator "$OPERATOR" --operator-confirms-controller-stopped
```

Record video. Empty the entire board. For each a1–h8 prompt, inspect **all** LEDs,
type `ONLY a1` etc. only if exactly that physical labelled square is blue, place
one actual piece there, and remove it as prompted. The original fresh SNAPSHOT
must report precisely its one expected bit, then zero. Do not change polarity or
orientation to conceal a failure. This is standalone supported-interface mapping,
not game feedback proof. Keep motors/magnet off.

The tool clears LEDs, sends STOP/STATUS and releases its exclusive link when done.
STOP invalidates carriage origin. Verify actual darkness and safe outputs. Its
initial aggregate BLOCKED for video review is expected **only if** all 64 rows and
cleanup succeeded. Any failed row remains a real mapping problem.

Copy the printed mapping ID and actual recording path into T3 using these reads;
type the actual values when each `read` waits:

```sh
read -r MAPPING_ID
read -r MAPPING_VIDEO
"$PY" -B "$DEMO/record_evidence.py" --run "$RUN" --kind hardware --label "mapping-$MAPPING_ID" --file "$MAPPING_VIDEO" --operator "$OPERATOR" --note 'TA reviewed final physical labels, all 64 single-bit sensor positions and only named LEDs; cleanup inspected'
```

`--label` must include `mapping-` plus the actual hex ID. A video attached with
the wrong label does not unlock #37–39. Those scripts independently require all
64 records and matching evidence before `begin`. Never run mapping while the
native application owns serial. If mapping cannot pass, record the blocker and
defer dependent hardware claims; do not modify code or swap in development boards.

## 4. Main service session: related tests together

In T1, launch once after mapping has released serial:

```sh
"$PY" -B "$DEMO/run_ta_service.py" --run "$RUN" --port "$PORT" --operator-confirms-controller-stopped
```

Paste **its exact printed native UI command into T2**. It binds the original UI
to the same explicit isolated DB and unique socket. Do not run a second launcher
or connect a recorder to that socket. Create `$WHITE`/`$BLACK` profiles using the
touchscreen if absent; enter the literal names held by those variables.

Keep T1/T2 running through Cards A–G below. Use T3 for the commands. Windows must
end while their required game state still exists; close markers **before** End,
preparing another game, Quit, disconnect or fault reset unless the card explicitly
tests those actions. Use unique window names for retries and retain every attempt.

### Card A — #23 + #37 + #38: one No-clock game

Use S: **No clock, Guidance ON**, standard board, Start. Begin LED windows:

```sh
"$PY" -B "$DEMO/demo_37_guidance_leds.py" begin --run "$RUN" --window led-guidance
"$PY" -B "$DEMO/demo_38_accepted_leds.py" begin --run "$RUN" --window led-accepted
"$PY" -B "$DEMO/demo_23_legal_destinations.py" begin --run "$RUN" --window guide-e2 --case e2
```

Immediately after the #23 marker prints, physically lift **only e2**. Show native
legal destinations e3/e4 and **only those two green LEDs**. Keep the piece lifted
while ending its #23 window:

```sh
"$PY" -B "$DEMO/demo_23_legal_destinations.py" end --run "$RUN" --window guide-e2
```

Return e2 and show guidance dark. After full synchronization:

```sh
"$PY" -B "$DEMO/demo_23_legal_destinations.py" begin --run "$RUN" --window guide-g1 --case g1
```

Immediately lift only g1: destinations f3/h3, only those LEDs green. End while lifted:

```sh
"$PY" -B "$DEMO/demo_23_legal_destinations.py" end --run "$RUN" --window guide-g1
```

Return g1, show clearing, wait for synchronization:

```sh
"$PY" -B "$DEMO/demo_23_legal_destinations.py" begin --run "$RUN" --window guide-a1 --case a1
```

Immediately lift only a1: blocked rook, **empty legal set and all LEDs dark**:

```sh
"$PY" -B "$DEMO/demo_23_legal_destinations.py" end --run "$RUN" --window guide-a1
```

Return a1. Lift e2 **again**, record its guidance, then physically complete e2e4.
Show old guidance replaced by **blue e2 / green e4**, with every other LED off:

```sh
"$PY" -B "$DEMO/demo_37_guidance_leds.py" end --run "$RUN" --window led-guidance
```

Physically play e7e5. Show **blue e7 / green e5 only**, replacing e2/e4. On White's
turn attempt g1g3: illegal red g1/g3 contrasts with accepted blue/green. Restore
g1 fully. End this game through the native UI; show all LEDs dark. Prepare the
next No-clock game (do not Start yet) and show old feedback stays absent:

```sh
"$PY" -B "$DEMO/demo_38_accepted_leds.py" end --run "$RUN" --window led-accepted
```

Acceptance: #23 ≤500 ms from identified lift to legal-destination availability,
including the empty set. Pi receipt alone omits upstream delay; record the marker
**before** the physical lift on video, so marker-to-result ≤500 ms conservatively
proves the full bound. A longer upper bound alone is BLOCKED. Two people help
make the marker/lift sequence practical; never lift early to improve a number.

#37 ≤500 ms to **actual illumination**, starting at receipt of destinations by
the feedback controller; #38 ≤500 ms to **actual blue/green output after successful
persistence**. Both require calibrated optical evidence, not ACK/RMT timing.
Clearing/replacement is functional; no extra clearing deadline is invented.

Evidence labels: `guide-e2`, `guide-g1`, `guide-a1`, `led-guidance`, `led-accepted`.
The repeated e2 lift requires another optical guidance annotation. See Section 8.

### Card B — #22 + #39 + #27 error: one No-clock game

Restore all pieces; finish S for the game just prepared: **No clock**, Start.
This shared error case does not need a running clock; #27's five-minute clock
visibility is separately tested on Card D.

```sh
"$PY" -B "$DEMO/demo_22_illegal_restore.py" begin --run "$RUN" --window illegal-restore --case illegal-restore
"$PY" -B "$DEMO/demo_39_rejected_leds.py" begin --run "$RUN" --window led-rejected
"$PY" -B "$DEMO/demo_27_display_updates.py" begin --run "$RUN" --window display-error --case error
```

1. Physically e2→e5. Show real MCU candidate, illegal rejection, unchanged accepted
   FEN/turn/history/records, and **red e2/e5 only**.
2. Leave it wrong; wait through UI refreshes. Toggle Guidance using its native
   button. Show the blocking error text and red warning remain.
3. Physically attempt d2→d4 without restoring e2. Show it is blocked.
4. Return the e5 pawn to e2 while d2 stays on d4. Show **partial restoration does
   not clear red e2/e5** or allow acceptance.
5. Return d4→d2. Wait for original full-board restoration confirmation and show
   the physical warning/error clear. Keep continuous video throughout.

Close the error/warning windows **before** resuming legal play:

```sh
"$PY" -B "$DEMO/demo_39_rejected_leds.py" end --run "$RUN" --window led-rejected
"$PY" -B "$DEMO/demo_27_display_updates.py" end --run "$RUN" --window display-error
```

Now physically e2→e4. Show Black to move and exactly one accepted stored move:

```sh
"$PY" -B "$DEMO/demo_22_illegal_restore.py" end --run "$RUN" --window illegal-restore
```

End the game normally after all markers close. #22/#39 have no numeric deadline.
#27 requires actual visible error/update latency ≤1 s and persistent blocking text.
No manual LED_CLEAR is allowed inside this test. Evidence labels: `illegal-restore`,
`led-rejected`, `display-error`. #39 needs red maps and continuous persistence
review, including each distinct partial configuration; duplicate polls do not
need duplicate optical annotations.

### Card C — #20: three fresh No-clock games

Use S with No clock and Guidance OFF for **each** case. Simultaneously lift e2
and d2 and verify actual **EVENT AMBIGUOUS**, not merely two separate LIFT events.
If no ambiguity occurs, retain that attempt and use a fresh named window/game.
Never inject an event. Do not restore the entire standard board before confirming,
because normal synchronization legitimately clears ambiguity.

Valid case, from a fresh standard active game:

```sh
"$PY" -B "$DEMO/demo_20_ambiguous_confirmation.py" begin --run "$RUN" --window amb-valid --case valid
```

Lift e2/d2 together; return d2 while e2 remains lifted. Put e2 on e4. Show the
confirmation request and no accepted advance while waiting. Use touchscreen
**Confirm move**, submit `e2e4`; only then should it validate, accept and persist.

```sh
"$PY" -B "$DEMO/demo_20_ambiguous_confirmation.py" end --run "$RUN" --window amb-valid
```

End normally, restore pieces, S again:

```sh
"$PY" -B "$DEMO/demo_20_ambiguous_confirmation.py" begin --run "$RUN" --window amb-invalid --case invalid
```

Create real ambiguity, return d2, put e2 on e5, then native Confirm `e2e5`.
Show rejection, unchanged accepted state/records and restoration request:

```sh
"$PY" -B "$DEMO/demo_20_ambiguous_confirmation.py" end --run "$RUN" --window amb-invalid
```

End normally, restore pieces, S again:

```sh
"$PY" -B "$DEMO/demo_20_ambiguous_confirmation.py" begin --run "$RUN" --window amb-mismatch --case mismatch
```

Create real ambiguity, return d2 but **keep e2 lifted and e4 empty**. Native
Confirm `e2e4`. It is legal but occupancy mismatches; show no acceptance/write:

```sh
"$PY" -B "$DEMO/demo_20_ambiguous_confirmation.py" end --run "$RUN" --window amb-mismatch
```

Then End normally. No numeric threshold is specified. Continuous accepted-board
synchronization is distinct from validating the proposed ambiguous move; the
observer verifies candidate rule/occupancy checks occur after explicit confirmation.
Evidence labels: `amb-valid`, `amb-invalid`, `amb-mismatch`.

### Card D — #27 overview + #28: one five-minute game

Prepare S: **5 min, Guidance OFF**. Check/verify the board but **do not Start yet**:

```sh
"$PY" -B "$DEMO/demo_27_display_updates.py" begin --run "$RUN" --window display-overview --case overview
"$PY" -B "$DEMO/demo_28_clocks.py" begin --run "$RUN" --window clocks --case clock-workflow
```

Press Start. Show both names, White to move, two five-minute clocks. Wait a few
seconds on White's turn, physically e2e4, then wait a few seconds on Black's turn.
Show turn/latest-move update and only active-clock countdown. Use **View position**
Previous/Next to verify e2e4 history, then Back to the active Game page. Clocks
continue while viewing. Close overview before clock recovery testing:

```sh
"$PY" -B "$DEMO/demo_27_display_updates.py" end --run "$RUN" --window display-overview
```

For #28: native Pause → wait with both frozen → native Resume → wait while running.
Physically unplug the **communication link only**, keeping intended PCB power safe.
Do not substitute UI Disconnect. Show detected loss and both clocks paused. Replug,
select the actual current device in the UI (enumeration can change), Connect,
restore/verify the accepted board, resolve the cause and use normal **Reset fault**
when required. Show clocks remain paused until explicit Resume and do not reset.
Resume, wait for running samples, native End, then wait a few seconds for stopped
samples while the UI remains open:

```sh
"$PY" -B "$DEMO/demo_28_clocks.py" end --run "$RUN" --window clocks
```

Do not prepare another game before this end marker. #27: actual visible updates
≤1000 ms, including initial clocks and subsequent White/Black remaining-time
samples. #28: switch/pause/stop after accepted events ≤500 ms; exact backend raw
times must freeze/persist. Rounded screen seconds do not prove raw preservation.
There is no separate numeric unplug-detection deadline. Update `$PORT` manually
for later service launches if re-enumeration changed it. Evidence labels:
`display-overview`, `clocks`. Never overlap this reset/disconnect sequence with #33.

### Card E — #27 check: a fresh game

Use S (5 min, Guidance OFF), Start, then:

```sh
"$PY" -B "$DEMO/demo_27_display_updates.py" begin --run "$RUN" --window display-check --case check
```

Physically play `e2e4 f7f6 d1h5`. Show native **Check.** on the actual screen:

```sh
"$PY" -B "$DEMO/demo_27_display_updates.py" end --run "$RUN" --window display-check
```

End this game normally; restore the board. Status visibility ≤1 s needs calibrated
physical-screen evidence, label `display-check`.

### Card F — #27 checkmate + #19 saved game

Use S (**No clock**, same two named profiles, Guidance OFF), Start:

```sh
"$PY" -B "$DEMO/demo_27_display_updates.py" begin --run "$RUN" --window display-mate --case checkmate
```

Physically play `f2f3 e7e5 g2g4 d8h4`. Show rules-detected checkmate and 0-1.
This **actual** completed game supplies #19 and the later #33 saved record:

```sh
"$PY" -B "$DEMO/demo_27_display_updates.py" end --run "$RUN" --window display-mate
"$PY" -B "$DEMO/checkoff_index.py" --run "$RUN"
```

Find the **completed 0-1 row with exactly those four moves and correct names**.
Do not assume ID 1: earlier games already exist. Type its actual numeric ID:

```sh
read -r GAME_ID
```

Write the ID in your results copy and retain it across reboot. #19 has **no begin
command**: its evaluator uses the service's real completion/persistence observations.
It requires ≤2000 ms completion-to-committed visibility, correct details/moves/FENs,
failed-write atomicity, restart and normal power-cycle evidence. It is not complete
until Sections 5–6. #27 mate visibility threshold remains ≤1000 ms.

Evidence label `display-mate` and an additional #19 hardware attachment (e.g.
`record-persistence`). Do not overwrite this record or substitute a generated game
as physical completion proof.

### Card G — #33 saved replay while another game is paused

Restore the physical board, S with No clock, Start and physically e2e4. Pause through
the UI **before** starting the replay observation. Keep this current game paused,
connected and physically unchanged:

```sh
"$PY" -B "$DEMO/demo_33_game_log.py" begin --run "$RUN" --window replay1 --saved-game-id "$GAME_ID"
```

Use the native back arrow to Home → History → the saved four-move 0-1 game. Show
names/details/result. From initial position press Next through all four plies,
then Previous through all four to the initial position. Return Home → Open current
game and show its accepted position/history, paused status and remaining values
unchanged. Do not touch pieces, resume, reset faults, End or disconnect inside
this window:

```sh
"$PY" -B "$DEMO/demo_33_game_log.py" end --run "$RUN" --window replay1
```

Then End the current game normally. #33 has no numeric deadline. Its observer
requires live PING/MCU replies and **no movement/STOP/CLEAR_FAULT commands**, not
just a stationary mechanism. Attach final-screen video both as `hardware/replay1`
and `replay-visible/replay1`. If native navigation is inaccessible, report BLOCKED;
never replace it with programmatic replay calls.

## 5. Close main; #19 real failed write in a separate DB

After every main window is closed and all active games ended, Quit Game in T2,
then Ctrl-C T1. Verify LEDs dark and safe motor/magnet outputs. The shared launcher
uses its own link for LED_CLEAR/STOP/STATUS, then original resource cleanup; it
never stops the normal controller. This is the first necessary main-service stop.

In T1 launch the already-existing **base** observer on the separate failure run:

```sh
"$PY" -B "$DEMO/run_demo_service.py" --run "$FAILURE" --port "$PORT" --operator-confirms-controller-stopped
```

Paste its printed UI command into T2. Create/select two test profiles in this
separate DB, S with No clock, Start, then native Pause. In T3:

```sh
"$PY" -B "$DEMO/demo_19_record_persistence.py" arm-failure --run "$FAILURE" --confirm-isolated-test-db
```

Native Resume, then **physically e2e4**. The real test-only SQLite trigger aborts
the original position update after its move insert attempt. Show “Move was not
saved,” paused/restoration state, unchanged accepted FEN/turn/history and no partial
move row. This is actual SQLite failure, not a mocked storage response.

Quit this UI, Ctrl-C **this failure service**, verify safe outputs. Only after its
run lock is released:

```sh
"$PY" -B "$DEMO/demo_19_record_persistence.py" disarm-failure --run "$FAILURE" --confirm-isolated-test-db
```

This drops only the named fixture trigger. Retain all test games, including an
interrupted failed-write game. Attach actual failure video under `$FAILURE` with
`--kind hardware --label failed-write`. No production DB is opened.

## 6. #19 manual restart and normal system power cycle

Restore physical pieces. In T1 manually relaunch the **main** run, without `--init`:

```sh
"$PY" -B "$DEMO/run_ta_service.py" --run "$RUN" --port "$PORT" --operator-confirms-controller-stopped
```

Paste its printed UI command into T2. History → saved `$GAME_ID`; verify names,
four moves, initial/resulting positions and 0-1 unchanged. This return from the
separate failure session also constitutes the required application restart;
there is no need for an extra artificial restart.

Quit UI/Ctrl-C service and verify safe outputs. Operator performs the Pi's normal
OS shutdown, waits for shutdown, cycles intended system power and boots normally.
**Do not pull power from a running Pi.** This guide contains no automated shutdown,
power control, service restart, or kill command.

After reboot, re-enter Section 2 variables with the **same directories and user**,
restore the actual `$GAME_ID`, check the actual port and run preflight `--run`.
Manually execute the same main launch command above and its printed native UI
command. Open saved History/Review again. Do not start new games. Record actual
normal-power-cycle evidence; changed Linux boot ID plus matching startup snapshots
are independently required by the #19 evaluator. Quit UI/Ctrl-C service again.

Attach the recording under the main run using `--kind power-cycle --label "$GAME_ID"`.
Reboot alone without recorded normal power removal is not that evidence.

## 7. Attach evidence with exact labels

For each row below, choose the **actual** file path and meaningful segment/calibration
notes. This command is an example invocation with variable values you enter, not
an example hardware result:

```sh
read -r LABEL
read -r VIDEO
read -r NOTE
"$PY" -B "$DEMO/record_evidence.py" --run "$RUN" --kind hardware --label "$LABEL" --file "$VIDEO" --operator "$OPERATOR" --note "$NOTE"
```

Repeat for all labels used. This copies evidence; it does not certify its contents.

| Main-run hardware labels | Coverage |
|---|---|
| `guide-e2`, `guide-g1`, `guide-a1` | #23 marker-before-lift, real source and expected set |
| `led-guidance`, `led-accepted`, `led-rejected` | #37–39 complete array/color/continuity and optical references |
| `illegal-restore` | #22 rejection, blocked move, full restoration, one accepted move |
| `amb-valid`, `amb-invalid`, `amb-mismatch` | #20 actual AMBIGUOUS, native confirmation and outcomes |
| `display-overview`, `display-error`, `display-check`, `display-mate` | #27 final-screen visibility, timing and persistence |
| `clocks` | #28 native clock workflow and physical link loss/recovery |
| `replay1` | #33 actual UI navigation and current paused game preservation |
| `record-persistence` | #19 physical four-move completion and restart verification |

Additional exact commands, with actual file variables entered first:

```sh
read -r REPLAY_VIDEO
"$PY" -B "$DEMO/record_evidence.py" --run "$RUN" --kind replay-visible --label replay1 --file "$REPLAY_VIDEO" --operator "$OPERATOR" --note 'TA reviewed saved four-move game details and all forward/back steps; separate current game stayed paused and unchanged'
read -r FAILURE_VIDEO
"$PY" -B "$DEMO/record_evidence.py" --run "$FAILURE" --kind hardware --label failed-write --file "$FAILURE_VIDEO" --operator "$OPERATOR" --note 'Final hardware; real e2e4 rejected by isolated SQLite ABORT; accepted state unchanged'
read -r POWER_VIDEO
"$PY" -B "$DEMO/record_evidence.py" --run "$RUN" --kind power-cycle --label "$GAME_ID" --file "$POWER_VIDEO" --operator "$OPERATOR" --note 'Normal OS shutdown, intended system power off/on, manual relaunch and exact saved-record review'
```

The mapping label from Section 3 is separate. The attacher has no bulk-loop,
`--tidr` or `--game-id` argument: use its existing `--kind` and exact `--label`.

## 8. Import actual display/LED measurements; retain BLOCKED if unavailable

Do this offline with UI/services closed. Use the new **read-only** index for actual
sessions, tokens, hashes and relevant raw states; it never starts a client/test:

```sh
"$PY" -B "$DEMO/checkoff_index.py" --run "$RUN" --window display-overview
"$PY" -B "$DEMO/checkoff_index.py" --run "$RUN" --window led-guidance
```

Repeat `--window` for the other named windows as needed. Use the existing JSON
templates as **test-only copies**; their defaults are deliberately incomplete.
Fill them from actual reviewed frames/instrument samples, not desired values or
socket timestamps. Detailed field specifications remain in
`README_DISPLAY_CLOCK.md` and `README_LED_FEEDBACK.md`.

#27 needs four annotation files. For overview include Start players/turn/clocks,
White/Black remaining-time sample tokens, accepted turn/latest move, and functional
View position history review. Check/mate need status samples. Error needs initial
visible error, error-cleared sample and continuous persistence through unrelated
Guidance action. Retain calibrated lower/upper Pi-monotonic visibility times,
uncertainty, frame references and the actual attached video hash.

```sh
cp -n "$DEMO/display_visibility_example.json" "$RUN/overview-visibility.json"
cp -n "$DEMO/display_visibility_example.json" "$RUN/check-visibility.json"
cp -n "$DEMO/display_visibility_example.json" "$RUN/mate-visibility.json"
cp -n "$DEMO/display_visibility_example.json" "$RUN/error-visibility.json"
```

Edit only those new copies, including each correct window name. `cp -n` leaves
existing files untouched; on a repeat use new names and update the import paths.
Then:

```sh
"$PY" -B "$DEMO/demo_27_display_updates.py" import-visibility --run "$RUN" --file "$RUN/overview-visibility.json"
"$PY" -B "$DEMO/demo_27_display_updates.py" import-visibility --run "$RUN" --file "$RUN/check-visibility.json"
"$PY" -B "$DEMO/demo_27_display_updates.py" import-visibility --run "$RUN" --file "$RUN/mate-visibility.json"
"$PY" -B "$DEMO/demo_27_display_updates.py" import-visibility --run "$RUN" --file "$RUN/error-visibility.json"
```

#37/#38 need full-array observed color maps plus calibrated optical onset bounds;
#39 needs initial red/partial/restored maps and continuous warning review, without
an invented numeric threshold. Include **every** lit square; all remaining 64
coordinates must actually have been inspected off. Unknown is not all-dark.

```sh
cp -n "$DEMO/led_optical_example.json" "$RUN/guidance-optical.json"
cp -n "$DEMO/led_optical_example.json" "$RUN/accepted-optical.json"
cp -n "$DEMO/led_optical_example.json" "$RUN/rejected-optical.json"
```

Fill these test-only copies using their actual `mv_call`/`dc_call` anchors, then:

```sh
"$PY" -B "$DEMO/demo_37_guidance_leds.py" import-optical --run "$RUN" --file "$RUN/guidance-optical.json"
"$PY" -B "$DEMO/demo_38_accepted_leds.py" import-optical --run "$RUN" --file "$RUN/accepted-optical.json"
"$PY" -B "$DEMO/demo_39_rejected_leds.py" import-optical --run "$RUN" --file "$RUN/rejected-optical.json"
```

Match `session`, `window` and evidence hash exactly. The accepted LED timing anchor
is after the original store transaction returns and before accepted-state swap;
the evaluator separately confirms successful persistence. ACK/PLATFORM/RMT completion
do not prove illumination. Clock milliseconds are raw backend values; native
screen seconds are rounded. Do not subtract unsynchronized camera/Pi clocks or
set `synchronized: true` without calibration. Missing equipment/calibration or
uncertainty spanning a deadline means BLOCKED, even when functionally correct.

## 9. Obtain all ten independent results

All main/failure sessions must have shut down cleanly; every observer start needs
a matching error-free stop. Do not run these as a `set -e` batch: BLOCKED/FAIL
exit nonzero and must be recorded independently, not silently skipped.

```sh
"$PY" -B "$DEMO/demo_19_record_persistence.py" evaluate --run "$RUN" --game-id "$GAME_ID" --expected-moves 'f2f3 e7e5 g2g4 d8h4' --white "$WHITE" --black "$BLACK" --result 0-1 --failure-run "$FAILURE"
"$PY" -B "$DEMO/demo_20_ambiguous_confirmation.py" evaluate --run "$RUN" --windows amb-valid amb-invalid amb-mismatch
"$PY" -B "$DEMO/demo_22_illegal_restore.py" evaluate --run "$RUN" --windows illegal-restore
"$PY" -B "$DEMO/demo_23_legal_destinations.py" evaluate --run "$RUN" --windows guide-e2 guide-g1 guide-a1
"$PY" -B "$DEMO/demo_27_display_updates.py" evaluate --run "$RUN" --windows display-overview display-error display-check display-mate
"$PY" -B "$DEMO/demo_28_clocks.py" evaluate --run "$RUN" --windows clocks
"$PY" -B "$DEMO/demo_33_game_log.py" evaluate --run "$RUN" --window replay1
"$PY" -B "$DEMO/demo_37_guidance_leds.py" evaluate --run "$RUN" --windows led-guidance
"$PY" -B "$DEMO/demo_38_accepted_leds.py" evaluate --run "$RUN" --windows led-accepted
"$PY" -B "$DEMO/demo_39_rejected_leds.py" evaluate --run "$RUN" --windows led-rejected
```

Results are versioned `result-N-<timestamp>.json` files; refer to the actual chosen
report, not only terminal output. Copy measured intervals, raw clock checks,
evidence paths and blockers into the results template. Exit codes: 0 PASS, 1 FAIL,
2 BLOCKED, 130 interrupted. NOT RUN is a preparation status, never a PASS. Do not
hide a failed valid observation by selecting only a favorable retry; retain all
attempts and let the TA record disposition.

Threshold summary:

| TIDR | Required acceptance |
|---|---|
| #19 | ≤2000 ms actual completion→committed record availability; correct records, atomic failure behavior, restart and normal power-cycle survival |
| #20 | Ambiguous candidate requires user confirmation before candidate rule/occupancy validation; invalid/mismatched confirmations do not advance; no numeric deadline |
| #22 | Illegal rejection leaves accepted state/records unchanged, blocks until full restoration, then permits legal play; no numeric deadline |
| #23 | Correct legal set, including empty, ≤500 ms from identified lift; report measured receipt interval separately from full-path proof |
| #27 | Required fields/check/checkmate/errors actually visible ≤1000 ms after backend update; blocking error persists |
| #28 | Only active clock decreases; switch/pause/stop ≤500 ms after accepted events; disconnect freezes both; exact remaining values preserved on resume |
| #33 | Correct native saved details and all steps; active paused game unchanged; no movement commands; no numeric deadline |
| #37 | Only legal destination LEDs physically lit ≤500 ms after controller receives destinations; return/completion clears guidance |
| #38 | Actual distinguishable source/destination response ≤500 ms after persisted acceptance; replacement, contrast and End/preparation clearing |
| #39 | Physical red source/destination warning persists through unrelated action and partial restoration, clears after confirmed full restoration; no numeric deadline |

## 10. Existing-launcher fallback and unresolved limits

If the new, statically reviewed unified launcher is not acceptable for live use,
use the existing launchers **one at a time**, stopping the demo UI/service safely
between groups. Use the same initialized main run and exact marker/evaluator
arguments above; repeat normal setup for each group:

| Existing launcher command (T1) | Capture with it |
|---|---|
| `"$PY" -B "$DEMO/run_led_service.py" --run "$RUN" --port "$PORT" --operator-confirms-controller-stopped` | Card A (#23/#37/#38), and #22/#39 error sequence; #27 error may be captured here as the LED observer includes dc records |
| `"$PY" -B "$DEMO/run_move_validation_service.py" --run "$RUN" --port "$PORT" --operator-confirms-controller-stopped` | Card C #20 (and separate #22/#23 if not already combined) |
| `"$PY" -B "$DEMO/run_display_clock_service.py" --run "$RUN" --port "$PORT" --operator-confirms-controller-stopped` | Cards D/E and #27 checkmate |
| `"$PY" -B "$DEMO/run_demo_service.py" --run "$RUN" --port "$PORT" --operator-confirms-controller-stopped` | Physically play a **new** designated #19 Fool's Mate here, then #33; use that actual ID for persistence/replay |

Extended launchers do not emit the legacy completion format #19 expects; merely
switching to the base launcher **after** an unobserved completion cannot recover
that missing timing. The fallback therefore needs another physical four-move
game under the base observer. The failure session and restart/power-cycle steps
remain separate and unchanged. Never run all four commands concurrently.

Remaining limits are recorded in `TA_COMMAND_AUDIT.md`: new unified runtime remains
untested; unavailable calibrated screen/LED timing blocks numeric claims; native
Game shows last move, with history through View position rather than a full live
move-list widget; the final checkmating move currently selects LED_CLEAR immediately
and does not establish a separate final-move indication. Do not modify production
to work around these limits. Every hardware result remains unassessed here.

## 11. Restore and retain

After the final history review, Quit UI/Ctrl-C only the demo-owned service, verify
physical outputs safe and LEDs dark, and restore pieces manually. Keep the entire
main/failure run, DB sidecars, event logs, mapping, annotations, reports and signed
results. Do not delete game records, trigger failures in the main/production DB,
remove a live socket, or automatically restart the normal application. The operator
may later start normal use through its normal supported workflow.
