# Team 24 Preliminary TIDR standalone demonstration plan

Planning date: 2026-11-26. Scope: TIDRs #4, #5, #6, #19, #20, #21, #22, #23, #27, #28, #33, #37, #38, #39.

**This change adds this plan only. No demonstration scripts have been implemented or run. No production source, firmware, configuration, database, or entry point needs modification for the proposed fixtures. Requirements unsupported by existing production interfaces remain BLOCKED; fixtures must not implement missing product behavior.**

Requirement authority: the user-supplied verified crosswalk from `Smart_Chess_Board_Team24_Preliminary_TIDR_Checkoff.docx` and Section 4.2 of `ECE 49022 - Product Development Plan - Update 3 - Fall 2026 v1.docx`. Those documents are not in this checkout; the supplied exact statements are preserved below. Repository specification targets do not replace these acceptance criteria.

## 1. Repository findings: actual interfaces

Paths in this section are relative to the repository root.

| Subsystem | Existing code/interface | Reuse and boundaries |
|---|---|---|
| ESP32-S3 sensing | `esp32/main/app_main.c`, `esp32/main/scb_core.c`; `scb_debouncer_update()` and `scb_move_tracker_process()` in `esp32/components/board_logic/src/sensor_matrix.c` | Existing flashed firmware selects eight rows, captures eight columns, debounces full-board snapshots and emits `BOARD`, `SENSOR`, `EVENT LIFT`, `EVENT MOVE`, and `EVENT AMBIGUOUS`. Nominal full scan is 10 ms, with two matching frames. These settings are not measured results. |
| Sensor diagnostics | `pi5/app/scb_link.py`: `ScbLink.open(port, exclusive=True)`, `request()`, `events`, `Frame.received_at`; `pi5/app/ui_hardware.py`: `fresh_snapshot()`, `stopped_status()` | `SCAN` returns latest stable occupancy, possibly old; `SNAPSHOT` waits for newly acquired stable frames and reports a frame number. `RAW`/`RAW TRACE` expose complete pre-debounce frames; `TIMING` exposes scan/debounce statistics. No sensor sampling loop is reimplemented. |
| Pi 5 rules and physical game | `pi5/rules/python/scb_rules.py`: `Game.legal_moves()`, `play()`, `fen()`, `status()`; `pi5/app/board_game.py`: `expected_occupancy()`, `occupancy()`, `fen_board()`, `PhysicalGame`; `pi5/app/ui_game.py`: `GameSession` | Native libchess is authoritative. The native UI uses `GameSession.on_board()`, `event()`, `commit()`, `synchronized()`, clock and recovery methods. Reuse the UI path for checkoff rather than creating a second validator. Stockfish is wrapped by `pi5/app/stockfish_engine.py`; these requirements do not require replacing the engine or online coaching. |
| Touchscreen | `pi5/ui/src/main.c`, `scb_ui.c`, `ui_bridge.c`; `pi5/app/ui_service.py`: `Server`, `UiCore`; `pi5/app/ui_launcher.py` | Native C/LVGL/SDL2 application on the Pi 5 and final official 5-inch Touch Display 2, 720 × 1280 DSI. Newline-delimited JSON over a private Unix socket carries commands and states. `UiCore.handle()` supports `connect`, `prepare`, `check`, `start`, `commit`, `guidance`, `pause`, `resume`, `end`, `history`, `review`, etc. |
| Socket ownership | `pi5/app/ui_service.py`: `Server.run()` | **Only one client is supported. A second connection is rejected.** A recorder must not connect beside the native UI or replace it. This corrects the earlier inspection concern: the second client is rejected rather than displacing the first. Use observations inside a demo-owned service process or passive external capture. |
| Records | `pi5/app/game_store.py`: `GameStore.start()`, `move()`, `checkpoint()`, `history()`, `review()`, `close()`; `pi5/storage/schema.sql` | SQLite schema v2: `players`, `games`, `game_moves`, `ui_state`, `board_settings`. `move()` transactionally inserts a move and updates the position. `GameSession.commit()` swaps the accepted rules position only after storage succeeds. `GameStore` construction can migrate a database; it is not a read-only inspector. |
| Database selection | `database_path()`, native UI `--database PATH`, `SCB_PLAYER_DB` | Production default is `~/.local/share/scb/players.sqlite3`. Both native UI and Python service must explicitly receive the same fresh test path. Server startup calls `interrupt_previous()`, another reason never to open the production database with a demo service. |
| USB/UART | `esp32/components/scb_transport/scb_transport.c`; `docs/USB_Protocol.md`; `ScbLink` | Current final target is bare ESP32-S3 on SCB Master PCB V3 with Sensor PCB V2.2. J5 native USB Serial/JTAG uses GPIO19/20, commonly `/dev/ttyACM0`; it is not a CP210x bridge. J5 USB does not power the PCB. J6 UART1 uses TX17/RX18 at 115200 8N1, 3.3 V. Transport is selected at firmware build time; do not reflash or switch it for these demos. |
| WS2812B feedback | `esp32/components/board_logic/src/led_grid.c`; RMT worker in `esp32/main/app_main.c`; `GameSession.feedback_command`, `UiCore.feedback_update()` | Existing `GUIDE mask`, `MARK source destination LEGAL/ILLEGAL`, `LED square r g b`, `LED_CLEAR` drive the final 64-square chain through GPIO21 and the PCB level shifter. LEGAL is blue source/green destination; ILLEGAL is red source/destination. Channels are capped at 32. ACK means queued; `PLATFORM` measures queue-to-RMT completion, not physical illumination. |

Additional evidence: `docs/PCB_Connection_Map.md`, `docs/ESP32_S3_Test_Guide.md`, `docs/Specification_Alignment.md`, `pi5/ui/README.md`, and `docs/validation/latest.json`. The validation record explicitly distinguishes host tests/builds from unperformed physical verification. Existing PTY, simulated GPIO, screenshot and fake-clock tests are useful development checks, not checkoff evidence.

Important gaps found in production:

- No command transfers expected occupancy from Pi to MCU. `GUIDE` is an LED destination mask, not an expected-board interface.
- No MCU mismatch response enumerates differences against an expected board. Pi synchronization compares full masks; the Board test UI independently marks differing cells in red. This does not establish a sensing-subsystem mismatch output on each move event.
- Firmware emits `AMBIGUOUS MULTI_SQUARE` / `MULTI_LIFT`, but does not know the accepted game position. It cannot flag expected-position mismatch errors itself.
- No timestamps report occupancy-comparison-to-mismatch-flag latency, actual LED light onset, or actual display visibility.
- Physical sensor/display/LED orientation remains subject to all-square verification. Diagnostic display coordinates may differ from firmware coordinates; record both. Do not patch mappings for the demonstration.

## 2. Proposed directory and script architecture

Only this Markdown file exists as part of this change. The following tree is a proposal, not implemented files:

```text
tests/tidr_demos/
  TIDR_DEMO_PLAN.md
  README.md                         # launch, ownership, hardware and TA checklist
  preflight.py                      # read-only checks; never stops services
  run_demo_service.py               # observe and invoke existing ui_service.main()
  common/
    paths.py                        # isolated paths and import bootstrap only
    evidence.py                     # JSON/text reports, timestamps, assertions
    observe.py                      # call-boundary observations, no replacement logic
    hardware_session.py             # exclusive serial ownership and cleanup
  demo_04_occupancy_comparison.py
  demo_05_state_discrepancies.py
  demo_06_mismatch_deadline.py
  demo_19_record_persistence.py
  demo_20_ambiguous_confirmation.py
  demo_21_expected_occupancy.py
  demo_22_illegal_restore.py
  demo_23_legal_destinations.py
  demo_27_display_updates.py
  demo_28_clocks.py
  demo_33_game_log.py
  demo_37_guidance_leds.py
  demo_38_accepted_leds.py
  demo_39_rejected_leds.py
  procedures/                       # one TA procedure per ID; physical move sequences
  runs/<run-id>/
    manifest.json                   # requirements, hardware identity, paths, instruments
    players.sqlite3                 # entirely separate demo database and sidecars
    events.jsonl                    # real observations with monotonic timestamps
    serial.jsonl                    # observed production requests and replies
    measurements.csv                # endpoints, duration, uncertainty, evidence reference
    evidence/                       # videos, instrument exports, frame annotations
    results.json
    results.txt
```

Each per-ID script orchestrates a procedure, observes production behavior, evaluates the specified conditions, and reports evidence. It must not implement sensing, validation, guidance generation, clocks, record transactions, or LED state machines. The #4/#6/#21 scripts may report BLOCKED with partial evidence; their filenames do not imply the missing interfaces exist.

### Execution modes

**A. Isolated UI demonstration (primary mode).** The operator first exits the normal application through its supported controls and confirms no other controller owns the final hardware. Manually launch a demo-owned service with an explicit test database and a unique short socket path, then manually launch the already-built native UI with the same database/socket. `run_demo_service.py` imports and calls the existing `ui_service.main()`; it does not copy `Server.run()` or substitute `GameSession`. Set `SCB_AUTOMATIC_MOTION=0` in these demo processes. The service remains the only serial owner and the native UI the only socket client.

The proposed observer uses Python's call/return profiling facilities in the demo-owned process and its threads to timestamp existing public operations (e.g. `GameSession.event`, `commit`, `GameStore.move`, `checkpoint`, `UiCore.handle`, `ScbLink.request`). It may snapshot public state at these boundaries. It must not monkeypatch functions, inject fake events, replace clocks, change return values, or suppress faults. Trace callbacks must be bounded, avoid tracing themselves, and record timestamp/observer overhead. If a required endpoint cannot be observed reliably, report BLOCKED rather than claiming precision. Timing under observation is reported as such.

Service → UI messages may be captured passively at the OS boundary for correlation with display video; do not add a socket client. Any tracing permissions or equipment requirements must be explicit in the manual procedure. Do not assume a tracing utility is installed. Do not record credentials; coaching stays off for these demos. For the display deadline, a later message-send timestamp alone is insufficient to stand in for an earlier backend update.

**B. Direct sensor/LED characterization (supporting mode).** With all controllers safely closed by the operator, use `ScbLink.open(actual_port, exclusive=True)` and its existing methods. Existing `board_diagnostics.values()` / `assess()` and `sensor_diagnostics` helpers can support characterization. Do not launch existing diagnostics beside the UI service. Their scan/LED software thresholds are supplementary and must not be substituted for these TIDR thresholds. Direct LED commands establish hardware capability only; #37–#39 acceptance must exercise production game-driven feedback.

**C. Offline evidence analysis.** Read captured evidence and only the demo database. Use SQLite `mode=ro` for inspection. Do not instantiate `GameStore` on the production database even to inspect it. No hardware port or socket is opened in this mode.

### Safety and isolation contract for later implementation

1. No automatic startup, flash, configuration edits, package setup, application rebuild, service shutdown/restart, process killing, or database migration outside the new test paths. Missing installed prerequisites produce BLOCKED. Use `python -B` / `PYTHONDONTWRITEBYTECODE=1` to avoid import artifacts in production directories.
2. Require explicit operator acknowledgment that the normal controller is safely closed before opening hardware. Read-only process/device-owner checks plus exclusive serial open are guards, not a guarantee against an uncooperative process. If ownership is occupied or uncertain, refuse to open. Never probe the production UI socket by connecting to it.
3. Resolve and validate fresh test database and socket paths before construction. Reject the production database path, symlinks/aliases to it, and existing non-demo databases. Use a short private temporary socket directory to meet the service's Unix-path limit; record it in the manifest. Create test profiles through the existing UI. Keep all test records and evidence; never purge game history.
4. Use final Pi 5, final sensor/master PCB, actual pieces/magnets, final WS2812B chain, and final touchscreen. Record identity and firmware capability replies; HELLO may be missed after boot. Do not flash substitute bench firmware or use development boards. Hall occupancy cannot prove piece type/color; the operator must verify those.
5. No demo sends `ARM`, `GOTO`, `MOVE`, `JOG`, `MAGNET ON`, calibration changes, polarity changes, or automatic fault reset. Normal sensing/LED/UI tests do not require mechanical transport. Do not reset cumulative timing counters to hide failures.
6. Bound waits and handle Ctrl-C, exceptions, and SIGTERM. For a direct-owned link, attempt `LED_CLEAR` and `STOP`, inspect safe outputs when communication works, then always close in `finally`; `ScbLink.close()` already sends STOP and releases the port. STOP invalidates the declared origin. Preserve faults. Never close another process's link.
7. In UI mode, use normal End/Quit controls for the demo session and the existing graceful service shutdown path; only demo-owned processes are involved. Never send cleanup commands through a second serial owner. If cleanup cannot be acknowledged, record it and require the operator to verify safe hardware outputs; do not declare successful cleanup from a closed file descriptor. Restore the physical board manually before returning it to normal use. Do not automatically relaunch production.
8. Normal power-cycle testing means the operator performs the Pi's supported shutdown, cycles intended system power, and manually relaunches the demo. Do not pull power from a running Pi or automate system shutdown. Save evidence to persistent storage, not a temporary RAM filesystem.

## 3. Evidence and result rules

Every script prints `TIDR #N: PASS`, `FAIL`, or `BLOCKED`, followed by assertions, measured values/units, and evidence paths. Suggested exit codes: 0 PASS, 1 FAIL, 2 BLOCKED, 130 interrupted. A requirement passes only when every clause has physical evidence. Partial assertions retain their own results and cannot upgrade a BLOCKED/FAIL aggregate.

- **PASS:** complete required physical procedure observed and all conditions met.
- **FAIL:** observed product behavior violates a condition or exceeds its deadline.
- **BLOCKED:** interface, observability, final hardware, instrument, or prerequisite prevents a complete test. Unsupported requirements are not repaired by fixtures.
- **NOT RUN:** planning/execution status, never a successful verification result. All hardware demonstrations are currently NOT RUN.

Reports retain actual BOARD masks/frame identifiers, candidate events, production expected occupancy, changed-square observations, FEN, accepted history, clocks, database rows and transaction outcomes as appropriate. A fixture may XOR observed masks to audit which squares differ; that is an independent reporting oracle, never a product mismatch flag. Preserve raw inputs and the requirement text/threshold in each report.

For timing, record both named endpoints, monotonic timestamps, acquisition method, sample count, each sample, maximum, and measurement uncertainty. Establish a common time base between software traces and optical evidence using a measured synchronization method; do not subtract unrelated camera and Pi clocks. A synchronized optical/instrument marker can be an external fixture, not replacement subsystem hardware. If uncertainty spans a deadline, report BLOCKED for that measurement. Do not invent tolerances for requirements without numeric limits.

Use high-speed video or synchronized photodetector/instrument capture for actual LED onset, and video of the final touchscreen for actual visible updates. Software ACK, RMT completion, socket state, desktop screenshots, preview PNGs, and terminal output alone cannot pass optical requirements. A recorded conservative interval can prove a deadline only if its start is demonstrably no later than the specified start event and its end no earlier than the required physical endpoint. Human stopwatch/keypress timing alone is insufficient for 100/500 ms boundaries.

## 4. Per-requirement scripts and TA procedures

### #4 — `demo_04_occupancy_comparison.py` — BLOCKED for literal subsystem requirement

> When a move event is output, the Board Sensing Subsystem shall compare the sensed occupancy of all 64 squares against the expected occupancy provided by the Processing & Game Logic Subsystem.

Reuse: real firmware BOARD/EVENT output; `GameSession.event()`, `commit()`, `synchronized()` and `board_game.expected_occupancy()`. TA procedure: verify all 64 physical sensor coordinates first; start an isolated PvP game, make a legal move, then repeat with an unrelated missing/extra piece and with several differences. Retain sensed and appropriate production expected masks at each move event, identifying all differences in the report. Distinguish accepted-position expectations from candidate post-move expectations.

The Pi implements full-mask occupancy checks, but the sensor firmware has no expected-occupancy input or expected-board comparison. A fixture XOR does not satisfy this requirement. Show partial Pi evidence to the TA, report the missing sensing handoff as BLOCKED, and request a subsystem-allocation clarification separately. No time threshold is specified.

### #5 — `demo_05_state_discrepancies.py` — partial firmware evidence; full requirement BLOCKED

> The sensing firmware shall compare between consecutive board states to instantly detect state discrepancies and flag invalid multi-piece displacements or board mismatch errors.

Reuse: `scb_move_tracker_process()` running in the existing firmware and its real `EVENT AMBIGUOUS` output. TA procedure: record stable snapshots, lift/return one piece, then displace multiple pieces so a single accepted frame contains multiple changes; restore, and separately create a game-position mismatch. Repeat physical attempts if changes span different frames; report what the sensor actually observed, not the intended gesture.

Check consecutive full-board differences and correlate actual ambiguous flags with multi-square/multi-lift changes. Record observed event latency without inventing a numeric meaning for “instantly.” Firmware can demonstrate ambiguity, but cannot compare to the accepted game board or produce that mismatch error. A generic AMBIGUOUS flag is not proof of a board-mismatch flag; mark the complete requirement BLOCKED unless the TA clarifies that its stated alternatives are satisfied by the demonstrated ambiguity behavior.

### #6 — `demo_06_mismatch_deadline.py` — BLOCKED

> If the sensed occupancy differs from the expected occupancy on one or more squares, then the Board Sensing Subsystem shall output a mismatch flag identifying each differing square within 100ms of the comparison.

Reuse only existing real snapshot and expected-position observations to document the gap. TA procedure: remove one piece; restore; introduce multiple missing and extra pieces. Show real masks and existing Board test red cells as partial evidence. The MCU has neither the expected-board input nor a per-square mismatch flag or its comparison timestamp. There is no supported path to measure **comparison → mismatch flag ≤100 ms**. Do not time an XOR implemented by this script or time SCAN replies and call it a pass. No production workaround is proposed.

### #19 — `demo_19_record_persistence.py` — feasible, pending physical execution

> The Game Record Store shall save game details, moves and positions within 2 s of completion. Move and position updates shall succeed together; failed writes shall not advance play, and records shall survive restart and normal power cycling.

Reuse `GameSession.commit()` / `end()` and `GameStore.move()` / `checkpoint()` with the separate real SQLite database. TA procedure:

1. Create real test profiles, play physical moves, and complete a game through the UI; separately exercise rules-detected completion (e.g. physically play Fool's Mate). Observe the actual completion decision/request and successful store return; read the committed details/moves/positions through a separate read-only SQLite connection. Measure completion → durable record availability **≤2 s**. Do not begin timing after the database commit.
2. For atomicity, observe consistent move/FEN updates using a read transaction. In a fresh fixture run, add an explicitly labeled SQLite trigger to the **test database only** that raises `ABORT` on the position update after a move insert has been attempted. Make a real physical move. Verify that both SQL changes rolled back and accepted FEN/history/turn did not advance. Remove only this fixture trigger after the demo owner releases the database. It is a deliberate real storage failure, not a mocked success or replacement store.
3. Optionally hold a separate test-database write lock beyond the production 250 ms connection timeout to exercise a real busy-write failure. Record possible failure of the subsequent pause checkpoint too; verify safe paused/restoration state and unchanged accepted records rather than assuming error recovery succeeded.
4. Exit normally and reopen against the same test DB; verify exact IDs, moves, positions, result and details. Operator shuts down/cycles/reboots the final Pi normally, manually relaunches, and repeats verification. Retain pre/post evidence. Application restart alone cannot pass the power-cycle clause.

No failed write may advance accepted play. Expected clock passage before rejection is not an accepted move. Report any failure as FAIL; missing power-cycle evidence remains BLOCKED for the complete requirement.

### #20 — `demo_20_ambiguous_confirmation.py` — feasible, pending physical execution

> The Move Validator shall require user confirmation for ambiguous sensor changes before applying rule and occupancy checks.

Reuse real `EVENT AMBIGUOUS`, `GameSession.event()`, `commit(explicit=True)` via the existing Confirm move UI. TA procedure: create a real ambiguous displacement, verify the confirmation prompt and unchanged accepted history, complete a plausible physical position without confirming, then submit the intended UCI through Confirm move. Repeat with illegal confirmation and legal confirmation whose physical occupancy is wrong.

Observe that candidate rule generation/post-move occupancy validation is gated behind explicit confirmation while ambiguous; invalid confirmation must still fail its existing checks. General continuous board synchronization is separate from validating the proposed ambiguous move; include this distinction in the evidence. Never invoke `commit(explicit=True)` automatically as a substitute for user confirmation. No numeric deadline.

### #21 — `demo_21_expected_occupancy.py` — matching gate feasible; sensing handoff BLOCKED

> The Game Logic Engine shall provide expected 64-square occupancy to the Board Sensing Subsystem and accept a move only when valid sensed occupancy matches.

Reuse `expected_occupancy()`, `GameSession.on_board()`, `commit()` and `UiCore.state()` (`expected_board`). TA procedure: play e2e4 normally; in a fresh attempt leave e4 empty or remove an unrelated piece before completing the candidate. Verify acceptance only for a fresh complete match and unchanged accepted history for mismatch. Check disconnected/stale hardware using actual disconnect/reconnect; do not inject a malformed BOARD line as physical proof.

`expected_board` in UI state is the accepted position; the candidate's post-move expected occupancy comes from the production helper in `commit()`. Do not confuse those masks. Record the full 64 bits and real board observations. The expected mask is not delivered to the MCU by any existing command, so the complete requirement remains BLOCKED even if the matching gate passes. No numeric deadline.

### #22 — `demo_22_illegal_restore.py` — feasible, pending physical execution

> The Game Logic Engine shall reject illegal moves without changing accepted records and block further moves until the board is restored.

Reuse `GameSession.commit()`, `restore`, `on_board()` and read-only test-DB inspection. TA procedure: from the initial position move e2→e5; observe rejection, restoration instruction and unchanged FEN/ply/records. Attempt another move before restoring: it must not be accepted. Restore the entire accepted physical position, then make a legal move and show exactly one new accepted record. Capture all attempted moves and snapshots; no time limit is invented.

### #23 — `demo_23_legal_destinations.py` — feasible with observed event boundaries

> With guidance enabled, the Move Validator shall provide legal destinations within 500 ms of an identified piece-lift event, returning an empty set when none exist.

Reuse PvP guidance, real `EVENT LIFT`, `GameSession.event()` and its `legal_destinations`/`feedback_command`. TA procedure: enable Guidance, lift e2 and verify e3/e4; return it, lift g1 and verify f3/h3; return it, lift the initially blocked a1 rook and verify an empty set. Retain the authoritative `Game.legal_moves()` filtered by the lifted square as expected evidence; do not implement a second move generator.

Measure identified-lift event reception → production legal destinations availability **≤500 ms**, retaining serial reception and service dispatch times separately. If only dispatch time can be observed, it omits queue delay and cannot pass the complete deadline. The LEDs are supporting evidence here; their physical deadline is independently tested under #37.

### #27 — `demo_27_display_updates.py` — feasible with synchronized physical-display capture

> The Game Display shall show players, turn, clocks, moves, status and errors within 1 s of backend updates, including when a king is attacked or cannot escape. Blocking errors shall remain until resolved.

Reuse the native UI, existing service states, `GameSession.state()` / `UiCore.state()`. TA procedure: show actual player names, accepted moves/turn/clocks; physically play f2f3, e7e5, g2g4, d8h4 to demonstrate checkmate, and use a separate legal sequence for check without mate. In a fresh run create an illegal move and leave it unresolved while navigating away/back and waiting; verify the error persists until full restoration.

For each required field/state, correlate the backend state transition with the first camera frame where it is actually visible on the final touchscreen. Require **≤1 s**. A 20 Hz service push target does not prove this. Missing visible fields or prematurely disappearing blocking errors are FAIL. Without a valid common time base or conservative endpoint bound, the timing assertion is BLOCKED.

### #28 — `demo_28_clocks.py` — feasible, pending physical execution

> Only the active player’s clock shall count down. Switching, pausing and stopping shall occur within 500 ms of accepted events; disconnection shall pause both clocks, and resumption shall preserve remaining times.

Reuse real monotonic `GameSession.tick()`, `tick_clock_only()`, `pause()`, `resume()`, `end()` and existing connection/fault recovery. TA procedure: use a 5-minute PvP game; wait on each player's turn, make physical accepted moves, pause/resume, end, then in a separate game unplug the actual USB link. Verify both clocks stop after disconnect detection; reconnect, restore, use the existing Reset fault control only after resolving the cause if required, then explicitly Resume.

Record acceptance boundary → switch/pause/stop effect **≤500 ms**, backend remaining times, and visible clocks. Record physical unplug → detected disconnect separately: the text supplies no separate numeric disconnect-detection deadline. Only the active clock may decrease; both must stay fixed while paused/disconnected/ended. Compare exact backend remaining times across pause/resume before new elapsed play, with no invented clock-accuracy tolerance. UI second rounding is not evidence of exact preservation.

### #33 — `demo_33_game_log.py` — feasible with observation of real commands

> Game Log shall display saved game details and support step-by-step move and position review without altering active games or issuing movement commands.

Reuse `GameStore.history()` / `review()` and native History/Review Previous/Next. TA procedure: save an actually played test game, start another physical game and pause it through normal controls, then open the saved game from the available History navigation. Step through every saved move and initial position; compare to committed rows/FEN. Return to the active game and verify accepted position/history, game identity, pause state and remaining clocks are unchanged. If the UI cannot reach saved-game History during an active game, report that portion BLOCKED; direct calls to `review()` alone cannot prove native navigation support.

Also inspect current-position review during a live unpaused game: its clock may legitimately advance, but accepted moves/position must not change due to review. Capture the complete existing serial request stream during replay and assert no `ARM`, `GOTO`, `MOVE`, `JOG`, `MAGNET ON` (or other actuator-enabling requests). Watch the real mechanism; physical nonmovement alone does not prove that no commands were issued. A production-owned `ScbLink.request()` observation in the isolated service covers application requests without opening a second serial connection. Keep ordinary heartbeat/snapshot traffic in the evidence.

### #37 — `demo_37_guidance_leds.py` — feasible with optical evidence

> The Board Feedback Controller shall illuminate only legal destinations within 500 ms of receiving them and clear guidance when the piece returns or the move completes.

Reuse production `legal_destinations`, `feedback_command`, `UiCore.feedback_update()`, `GUIDE` and `LED_CLEAR` through existing RMT hardware. TA procedure: enable Guidance, lift the test pieces used for #23, photograph all 64 squares and verify exactly the legal destination set is illuminated (empty for the blocked rook). Return the piece and verify clearing; repeat and complete a legal move.

Measure production receipt/availability of destinations at the feedback-controller boundary → actual illumination **≤500 ms**. Record this boundary separately from MCU command arrival; starting only at LED ACK omits transport/scheduling. New accepted source/destination feedback may replace guidance on completion (#38); verify that the old guidance pattern clears, rather than requiring all LEDs to remain dark. No clearing deadline is specified. Wrong/extra squares or retained old guidance are FAIL.

### #38 — `demo_38_accepted_leds.py` — feasible with optical evidence

> Accepted moves shall receive distinguishable source and destination LED indications within 500 ms, distinct from illegal-move feedback. New feedback shall replace old indications, with clearing at game completion or preparation.

Reuse `GameSession.commit()`, `feedback_command`, existing `MARK ... LEGAL` / `ILLEGAL`, `LED_CLEAR`. TA procedure: accept e2e4 and observe blue e2/green e4; accept e7e5 and show previous indications replaced; in another attempt compare red illegal-move feedback. End and prepare games through normal controls, verifying clearing. Include rules-detected completion, which sets LED_CLEAR in production; report the observed transition rather than fabricating a final-move pulse.

Measure accepted-move boundary after successful persistence → actual distinguishable illumination **≤500 ms** using synchronized trace/video. Capture source, destination and the whole previous pattern. ACK/RMT timing alone cannot pass. If completion suppresses an indication required by the TA's interpretation, record FAIL for the observed behavior and ask for interpretation without adding a fixture indication.

### #39 — `demo_39_rejected_leds.py` — feasible with optical evidence

> Rejected moves shall illuminate identified source and destination squares until board restoration is confirmed, then clear the warning.

Reuse illegal `commit()` path, `restore`, `on_board()`, `MARK ... ILLEGAL` and `LED_CLEAR`. TA procedure: make e2→e5; show red source/destination. Leave the board wrong, toggle Guidance off and attempt another move: warnings must persist. Partially restore while another square remains wrong: warnings must still persist. Restore the complete accepted board and observe the production confirmation and physical warning clearing. Capture the entire hold/partial/full-restoration sequence; no numeric deadline is specified. Do not clear LEDs manually to simulate successful recovery.

## 5. Checkoff sequence and current disposition

1. Review this architecture and provision only missing demo artifacts after approval of scope. No production patches are part of this plan.
2. On final hardware, operator closes the normal controller safely. Run read-only preflight; verify actual polarity and all 64 sensor/LED coordinates using existing interfaces. Mismapped or unavailable hardware blocks dependent tests.
3. Run #5 firmware characterization, then the isolated PvP session for #20/#22/#23/#28; collect shared evidence once where appropriate, retaining per-ID assertions.
4. Capture final-display evidence for #27 and optical LED evidence for #37/#38/#39. Run #19 real failure and normal power-cycle procedures and #33 replay checks.
5. Show #4/#6/#21 interface gaps and partial evidence explicitly. No rerouting of requirements or changing firmware is authorized to obtain a pass. #5's complete wording also needs the noted interpretation or remains BLOCKED.
6. Present a per-ID results table and measurement evidence to the TA. Exit the demo gracefully, verify outputs safe, restore physical pieces manually, retain test records, and leave production restart to the operator.

Current status: **all demonstrations NOT RUN**. Architectural blockers: #4, #6 and the sensing handoff of #21; #5 has a firmware ambiguity demonstration but lacks expected-board mismatch reporting. Other demos are feasible subject to final hardware, observability, prerequisite checks and actual behavior; feasibility is not a PASS. No existing production file needs modification to create or run the feasible standalone fixtures. Satisfying unsupported product behavior may require a separate future design decision, outside this request.
