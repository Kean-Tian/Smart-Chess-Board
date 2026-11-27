# Checkoff command and compatibility audit — 2026-11-26

Method: read all existing README files, argument definitions, observers, path
guards, evaluators, launchers and relevant native UI/source interfaces. Static
syntax/command review only. **No demo, unit test, preflight, database inspection,
service, UI, mapping capture or hardware test was executed in this consolidation
phase.** Previously reported 31 passing tests are historical, not new validation
of the unified additions.

## Commands and formats

| Existing entry point | Confirmed arguments / data format | Consolidated usage |
|---|---|---|
| preflight.py | `--init PATH --purpose records/failure --port PORT`; later `--run PATH` | Initialize only before ownership; failure after init still leaves metadata |
| run_demo_service.py and observer wrappers | `--run PATH --port PORT --operator-confirms-controller-stopped` | Exactly one foreground service and its printed native UI command |
| verify_led_mapping.py | `--run --port --operator --operator-confirms-controller-stopped` | Interactive direct serial characterization only while every controller is closed |
| demo_19_record_persistence.py | `arm-failure/disarm-failure --run --confirm-isolated-test-db`; `evaluate --run --game-id --expected-moves --white --black --result --failure-run` | No `begin` action. Needs legacy `call/return GameSession.commit/end` records |
| demo_20_ambiguous_confirmation.py | `begin --run --window --case valid/invalid/mismatch`; `end --run --window`; `evaluate --run --windows ...` | Three fresh standard No-clock games |
| demo_22_illegal_restore.py | Same window form; case `illegal-restore` | Can share standard No-clock error sequence with #39 and #27 error |
| demo_23_legal_destinations.py | Same window form; case `e2/g1/a1` | Begin before each physical lift, end while lifted, return before next case |
| demo_27_display_updates.py | Cases `overview/check/checkmate/error`; `import-visibility --run --file`; `evaluate --windows` | Overview begins before Start and needs 5 min; error can share No-clock #22/#39 |
| demo_28_clocks.py | Case `clock-workflow`; normal `begin/end/evaluate --windows` | Begin before five-minute Start; end after End and frozen samples, before another game |
| demo_33_game_log.py | `begin --run --window --saved-game-id`; `end/evaluate --run --window` | Singular `--window`, not `--windows`; active current game already paused |
| demo_37/38/39 | `begin/end --run --window`; `import-optical --run --file`; `evaluate --windows` | No `--case` argument; script assigns it; verified mapping is mandatory before begin |
| record_evidence.py | `--run --kind hardware/power-cycle/replay-visible --label --file --operator --note` | Exact labels; each call copies source file and records SHA-256 |
| generate_test_game.py | `--init` optional, `--run --operator-confirms-demo-closed`; optional paired player IDs | Valid fixture only; optional, not needed in primary physical workflow |

## Findings and mitigations

| Finding | Practical consequence / mitigation |
|---|---|
| Extended observers replace legacy commit/end event formats | Existing LED/display/move launchers alone cannot supply #19's timed completion. New `run_ta_service.py` adds original `Observer.observe` calls for those two methods while retaining inherited mv/dc/LED records. Earlier files are untouched. Runtime remains untested; existing base-launcher fallback requires a new physically completed #19 game under that observer. |
| Native UI socket supports one client | Never attach a recorder/client or launch a second UI/service. New additions only profile calls or read saved files. |
| Launchers print a direct native binary command | Use it verbatim in T2. `pi5/start.sh ui` would spawn another service and use default paths; do not run it alongside the demo. |
| Default production DB has migrations and service startup interrupts previous active/paused games | Always pass isolated explicit paths. Read-only index uses `database_snapshot` rather than constructing GameStore. Never inspect production via a GameStore constructor. |
| Absolute/UID-bound run manifests | Initialize on final Pi, retain path and login across restart/power cycle; do not transfer an unchanged Mac run folder and expect it to load. |
| Game IDs are not predictable after earlier cases | Read actual completed four-move 0-1 game ID using the read-only index; do not copy README example ID 1. Same ID used for #19, #33 and power-cycle evidence label. |
| `SCB_UI_TEST_MODE` checks environment presence | Even value `0` disables real bridge behavior. Unset in demo terminals, along with stale dummy-video/transport overrides. No persistent configuration edit is prescribed. |
| Preflight checks existence, not every native build property | Confirm ARM64/Pi builds, actual desktop/touchscreen and compatible deployed firmware. Missing/unsupported prerequisite is BLOCKED, not permission to flash/rebuild production during checkoff. |
| Group wrappers are not all explicitly named in process inventory | Treat process-name inventory as advisory. `fuser`, exclusive serial open, run/socket locks and explicit operator ownership confirmation remain required. A second wrapper must never be started while the first owns hardware. |
| `--init` refuses reuse and can create metadata before returning BLOCKED | On retry use `--run`, or choose another unique run name. Never delete an old run or mix main/failure DB purposes. |
| Active/paused game state is part of marker guards | #20/#22/#23 and LED begins require standard active setup; #27 overview/#28 begin before Start; #33 requires a different active paused game. The guide separates these states explicitly. |
| Clock controls are 0/5/10 min; no new custom time | Use No clock for unchanged-record scenarios; 5 min for #27 overview/#28. No-clock #27 error is supported by its evaluator and avoids interfering with #22/#39 equality checks. |
| #33 forbids writes and STOP/DISARM/IDLE/CLEAR_FAULT during replay | Pause before begin; do not overlap with #28, fault reset, End, Quit or service shutdown. Existing Home→History navigation is available in source; actual final UI still needs verification. |
| End, prepare and cleanup select LED_CLEAR | Keep them outside #39 hold and #33 windows. #38 explicitly tests End/preparation within its own window. |
| #19 failure trigger aborts position UPDATE only in failure DB | Pause, arm, Resume, physically move; Quit/stop failure service before disarming its trigger. Never arm in main/production DB or leave two serial owners active. |
| Shutdown is required before normal power removal | Operator uses supported OS shutdown; no automated shutdown/kill/power command is introduced. Restart alone does not prove normal power-cycle survival. |
| UI/USB enumeration can change after #28 | Re-select actual port via UI and update shell PORT for later launches; do not modify firmware/config. |
| #23 lacks MCU-internal identification timestamp | Pi receipt measurement is partial; valid pre-action marker-to-result upper bound ≤500 ms can prove the full deadline. Otherwise BLOCKED; no assumed transport latency. |
| #27/#37/#38 require actual optical endpoints | Socket transmission/ACK/RMT stats alone cannot pass. Calibration/uncertainty and matched physical evidence are mandatory. New templates remain unfilled until actual measurements exist. |
| Native active Game has latest move, not full live list | Use native View position for history; if a full live list is demanded, report unsupported capability BLOCKED. |
| Rules-terminal move immediately selects LED_CLEAR | #38 requested two-nonterminal-move/manual-End fixture does not establish separate final-mating-move indication. Report this scope limitation; do not add a fake flash. |
| Mapping capture initially returns aggregate BLOCKED for video review | Inspect all 64 rows/cleanup; attach video with `mapping-<actual id>`. LED begin guard independently validates mapping. Do not treat a failed mapping row as merely missing video. |
| Mapping records order captures/windows by monotonic time without boot binding | Keep mapping and all LED windows in the same boot, before #19 power cycling. Evaluate those original windows without appending new post-reboot mappings. Use a new run for later/differently assembled hardware rather than mixing clock domains. |
| Manual annotation `cp` can overwrite prior test evidence | Consolidated guide uses no-clobber copies; on repeat preserve prior filled files, use new names and update import command. Never overwrite actual measurements with templates. |
| Imports and evidence attachments are snapshots/copies | Later edits to the source JSON do not change an imported copy; import a new reviewed version. Full recordings attached repeatedly consume repeated space; reserve storage and retain frame/calibration provenance. |
| Error-free stop records are required | Gracefully close all sessions before final evaluation. Do not kill a hung process or remove live sockets to force success. A retained observer error can block a session (and #19's run-wide error check); preserve it and use a properly documented new run if necessary. |
| README selftest commands are engineering checks | They are intentionally not run during this task. Old PASS examples are labeled examples, not hardware evidence. |

## New additions and static scope

`run_ta_service.py` imports the existing shared launcher. Its only extra behavior
is to select a demo subclass and preserve original legacy observation records.
`TAObserver` invokes the existing base method, not a copied transaction or game
loop. The original pending dictionary and the mv/dc pending dictionaries are
separate. Existing subclass dispatch skips those legacy records, so this adds one
legacy pair rather than duplicating a pair already emitted. Calls/returns and
snapshot availability include observation overhead, as do earlier measurements.

`checkoff_index.py` only reads guarded test-run files/SQLite snapshots and prints
game IDs, mapping/evidence metadata and candidate annotation tokens. It never opens
a serial port, a socket, a writable GameStore, a process, or a control API.

Syntax and documentation command checks do not establish runtime or final-hardware
correctness. No new test-pass count is claimed. Before actual checkoff, the operator
may choose the optional unified path or the documented existing-launcher fallback;
both retain all existing product logic and physical verification requirements.
