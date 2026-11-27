# TIDR #20, #22 and #23 — standalone final-board demonstrations

This supplements the existing `README.md`. Only new files were added for this
group; earlier demo files and all production files remain unchanged. No physical
checkoff has been performed by installing or testing this code.

## Shared infrastructure and launch

The new `run_move_validation_service.py` calls the **existing shared launcher's
main function**, including its preflight, run lock, exclusive original serial
owner, isolated DB/socket, native service and graceful cleanup. It temporarily
selects `MoveObserver`, a subclass of the existing demo Observer, **only in memory
in the demo module**. No production class or method is replaced or patched.
The original production `Server.run`, `UiCore`, `GameSession`, native chess rules
and GameStore execute normally. The subclass records additional public fields and
call/return boundaries; it never injects events or changes return values.

The normal controller must be safely exited **by the operator** before launch.
Close other serial terminals. Never run the old and new demo launchers together.
Only the native UI connects to the private UI socket; the scripts below are
read-only observers/analyses, not another UI or serial client. Use final Pi 5,
final touchscreen, final sensor/master PCB and actual magnetic chess pieces.

On the Pi desktop, from the repository root:

```sh
DEMO="$PWD/tests/tidr_demos"
PY="$PWD/pi5/.venv/bin/python"
RUN="$DEMO/runs/move-validation"

"$PY" -B "$DEMO/preflight.py" --init "$RUN" --purpose records --port /dev/ttyACM0
"$PY" -B "$DEMO/run_move_validation_service.py" --run "$RUN" --port /dev/ttyACM0 --operator-confirms-controller-stopped
```

Replace `/dev/ttyACM0` with the actual device. If the run already exists, use
`preflight.py --run "$RUN" ...` instead of `--init`. Missing prerequisites or
uncertain ownership block launch. No setup/build/flash or service management is
automated. In a **second desktop terminal**, paste the native UI command printed
by the launcher; it supplies the explicit isolated database/socket. Do not launch
`pi5/start.sh ui` alongside it.

Use **Players** to create two test profiles. Choose **Two players / No clock**,
assign those profiles, arrange the actual standard board, **Check position**,
confirm physical types/colors and **Start**. Verify all-square mapping/polarity
before checkoff. Sensor occupancy cannot identify piece types. This group does
not need a completed saved game or generated sensor input.

In a **third terminal**, define the same DEMO/PY/RUN variables and run the window
commands below. Each `begin` checks an active, unpaused, connected standard game
and snapshots its isolated records. It records a timestamp **before** the physical
action. Each `end` snapshots the resulting real state. End the window **before**
End game, Pause, Quit, or preparing another game. Unique names retain every
attempt; `--windows` selects which attempts to evaluate. No records are deleted.

The legacy launcher does not expose all required observations; these scripts
report BLOCKED if only legacy traces are available.

## #20 — ambiguous changes require confirmation

Use three fresh standard-position games, one per case. Guidance can stay off.
Record video showing the final board, touchscreen prompts and confirmations.

### Valid confirmation

```sh
"$PY" -B "$DEMO/demo_20_ambiguous_confirmation.py" begin --run "$RUN" --window amb-valid --case valid
```

1. Physically lift e2 and d2 nearly simultaneously so the MCU reports
   `EVENT AMBIGUOUS ...`. Both changes must fall into an accepted multi-square
   frame. If firmware reports separate lifts instead, this attempt is not proof
   of ambiguity: retain it and try a new named window/fresh game.
2. Observe the actual ambiguity/Confirm move message. Return d2 while e2 stays
   lifted, then put that pawn on e4. **Do not return the whole board to its
   accepted starting position**, which normally clears ambiguity.
3. Leave the completed e2e4 position unconfirmed for a visible interval. Show that
   accepted position, turn and move history have not advanced.
4. Use the existing touchscreen **Confirm move** editor to submit `e2e4`. Only now
   should the original rule/occupancy checks accept it and save one move.

```sh
"$PY" -B "$DEMO/demo_20_ambiguous_confirmation.py" end --run "$RUN" --window amb-valid
```

End this test game normally without inventing an outcome. Restore all physical
pieces, then start a new standard test game for each following case.

### Invalid confirmation

```sh
"$PY" -B "$DEMO/demo_20_ambiguous_confirmation.py" begin --run "$RUN" --window amb-invalid --case invalid
```

Lift e2/d2 together and verify actual AMBIGUOUS. Return d2 and put the e2 pawn on
e5. Submit `e2e5` through Confirm move. Show illegal rejection/restoration prompt,
unchanged accepted FEN/turn/history and unchanged saved records. Then:

```sh
"$PY" -B "$DEMO/demo_20_ambiguous_confirmation.py" end --run "$RUN" --window amb-invalid
```

### Legal confirmation with physically mismatched occupancy

```sh
"$PY" -B "$DEMO/demo_20_ambiguous_confirmation.py" begin --run "$RUN" --window amb-mismatch --case mismatch
```

Lift e2/d2 together, verify actual AMBIGUOUS, return d2 and **keep e2 lifted with
e4 empty**. Confirm `e2e4` through the touchscreen. The candidate is legal but its
physical occupancy is wrong; show that nothing is accepted or stored. Then:

```sh
"$PY" -B "$DEMO/demo_20_ambiguous_confirmation.py" end --run "$RUN" --window amb-mismatch
```

The evaluator distinguishes candidate rule/post-move occupancy checks from the
normal continuous comparison to the already accepted board. It records exact
rule-check order and the native Server→UI-handler→commit path. Neither a direct
Python `commit(explicit=True)` nor a fake AMBIGUOUS line passes physical checkoff.
No numeric latency threshold is invented for #20.

## #22 — illegal move, block, restore, resume

Start another standard-position PvP/No clock game, then:

```sh
"$PY" -B "$DEMO/demo_22_illegal_restore.py" begin --run "$RUN" --window illegal-restore --case illegal-restore
```

1. Physically move e2→e5. Observe real `EVENT MOVE e2e5`, illegal rejection and
   restoration instruction. Show accepted FEN/turn/history unchanged.
2. Leave e2/e5 wrong and physically move d2→d4. Observe the second real candidate
   report and show that the game blocks it. Do not use a scripted confirmation
   as a substitute for this physical attempt.
3. Restore **both** disturbed pieces to e2 and d2; e4/e5/d4 must be empty. Wait for
   full-board synchronization and the restoration flag to clear. Partial
   restoration must not count as restored.
4. Physically play e2→e4. Show normal acceptance, Black to move and exactly one
   saved move. End the observation while the game is still active:

```sh
"$PY" -B "$DEMO/demo_22_illegal_restore.py" end --run "$RUN" --window illegal-restore
```

The evaluator compares every saved column at rejection, observes absence of
GameStore move writes during the blocked interval, and audits final FEN/occupancy
using the production engine. No clock avoids unrelated clock persistence changes.
No numeric deadline is invented for #22.

## #23 — correct legal destinations and ≤500 ms response

Start a fresh standard PvP/No clock game. Enable **Guidance** through the existing
setup or active-game UI. No accepted move is made during these cases.

```sh
"$PY" -B "$DEMO/demo_23_legal_destinations.py" begin --run "$RUN" --window guide-e2 --case e2
```

Immediately after the marker is printed, lift **only e2**. Expected destinations
are **e3/e4**. Keep it lifted while ending the window:

```sh
"$PY" -B "$DEMO/demo_23_legal_destinations.py" end --run "$RUN" --window guide-e2
```

Return the pawn to e2 and wait for full synchronization, then repeat:

```sh
"$PY" -B "$DEMO/demo_23_legal_destinations.py" begin --run "$RUN" --window guide-g1 --case g1
# Immediately lift only g1. Expected destinations: f3/h3.
"$PY" -B "$DEMO/demo_23_legal_destinations.py" end --run "$RUN" --window guide-g1

# Return g1 and wait for synchronization before the next begin.
"$PY" -B "$DEMO/demo_23_legal_destinations.py" begin --run "$RUN" --window guide-a1 --case a1
# Immediately lift only a1. Expected destinations: empty set.
"$PY" -B "$DEMO/demo_23_legal_destinations.py" end --run "$RUN" --window guide-a1
```

Return the rook afterward. The observer captures actual production
`Game.legal_moves()` results and `GameSession.event()` return state. Offline
analysis uses the same authoritative native rules, including the empty-set case.
LEDs are supporting observations here, not the deadline endpoint of #23.

**Timing evidence matters:** the firmware supplies no timestamp for its internal
piece-lift identification. The tool therefore records both:

- Pi event-receipt → first observed completed legal-destination result, including
  service queue/dispatch time and observer overhead.
- Pre-action marker → completed result, a conservative full-path upper bound.

Use two people: one starts `begin`, the other lifts immediately **after** the
printed marker. Video must show the marker preceding the physical lift. An
observed marker-to-result interval ≤500 ms proves the required event-to-result
deadline because the physical lift/identification occurred after that marker.
Do not lift early to improve the number. One identified lift per window avoids
reusing the early marker for a later repeated lift.

If the conservative bound exceeds 500 ms, it is **BLOCKED**, not automatically a
product failure: operator reaction may have consumed the interval. A receipt-only
interval below 500 ms cannot remove that blocker. If even the production rule
query starts >500 ms after Pi receipt, the deadline is demonstrably violated and
reports FAIL. Repeat an inconclusive attempt in a new named window or retain it
as BLOCKED; do not reset counters, invent an upstream delay or change firmware.

## Attach evidence, clean up and evaluate

Use the **existing** evidence tool. Attach an actual final-hardware/UI recording
for each selected window, with `--label` exactly equal to that window's name.
The same recording can cover several windows, but each attachment must identify
the relevant segment and actions. Example invocation using a real file:

```sh
"$PY" -B "$DEMO/record_evidence.py" --run "$RUN" --kind hardware --label amb-valid --file /path/to/actual-video.mp4 --operator 'Your name' --note 'Final Pi 5/touchscreen/PCB; amb-valid segment: real AMBIGUOUS, waiting and native Confirm move'
```

Repeat with labels `amb-invalid`, `amb-mismatch`, `illegal-restore`, `guide-e2`,
`guide-g1`, `guide-a1`. For guidance explicitly document marker-before-lift ordering.
The TA reviews physical content; the script verifies attachment integrity, not
the truth of a video. Missing evidence remains BLOCKED.

After all windows are closed, End the current demo game normally, Quit the UI,
then Ctrl-C the **demo-owned** service terminal. Original shared cleanup clears
LEDs, requests STOP/STATUS through that same owner and closes resources. Verify
physical safe outputs, restore pieces manually and retain all records. Never
stop/restart the normal application automatically. Evaluate only after clean
service shutdown so a complete trace can be checked:

```sh
"$PY" -B "$DEMO/demo_20_ambiguous_confirmation.py" evaluate --run "$RUN" --windows amb-valid amb-invalid amb-mismatch
"$PY" -B "$DEMO/demo_22_illegal_restore.py" evaluate --run "$RUN" --windows illegal-restore
"$PY" -B "$DEMO/demo_23_legal_destinations.py" evaluate --run "$RUN" --windows guide-e2 guide-g1 guide-a1
```

Versioned `result-20/22/23-<timestamp>.json` reports retain checks and actual timing
endpoints/values. `events.jsonl` contains original sensor replies, calls, query
order and states; `move_windows.jsonl` retains test boundaries and DB snapshots.
Exit codes remain 0 PASS, 1 FAIL, 2 BLOCKED, 130 interrupted. Missing cases,
uncorrelated events, legacy observations and synthetic traces cannot pass.

**Example only — not an executed hardware result:**

```text
TIDR #20: BLOCKED
  BLOCKED: amb-valid: final hardware and visible UI evidence — ...
TIDR #22: PASS
  PASS: illegal-restore: exactly one legal move persisted — ...
TIDR #23: BLOCKED
  BLOCKED: guide-e2 lift 1: response <=500 ms — {'pi_receive_to_availability_upper_ms': 3.2, 'pre_action_to_availability_upper_ms': 814.0, ...}
```

## Software validation only

```sh
python3 -B -m unittest discover -s tests/tidr_demos/selftests -v
```

New selftests execute original GameSession/GameStore/native rules with explicitly
synthetic board input, tag every observation synthetic, and never launch a
service/UI/socket/serial link. They verify guard order, real DB preservation,
restoration, legal/empty guidance, wrong-guidance detection and conservative timing
classification. Such tests validate the framework and cannot complete checkoff.
