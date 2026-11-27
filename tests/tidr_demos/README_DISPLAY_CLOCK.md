# TIDR #27 and #28 — final touchscreen and original chess clocks

This adds documentation for the new group without changing earlier demo files.
No hardware result is supplied. Software tests, socket writes and backend states
cannot establish actual screen visibility.

## Launch: operator action only

Use the final Pi 5 desktop, final touchscreen, final PCB/sensors and real pieces.
Exit the normal controller safely yourself; close serial terminals. From the
repository root, in the service terminal:

```sh
DEMO="$PWD/tests/tidr_demos"
PY="$PWD/pi5/.venv/bin/python"
RUN="$DEMO/runs/display-clock"

"$PY" -B "$DEMO/preflight.py" --init "$RUN" --purpose records --port /dev/ttyACM0
"$PY" -B "$DEMO/run_display_clock_service.py" --run "$RUN" --port /dev/ttyACM0 --operator-confirms-controller-stopped
```

For an existing run, replace preflight `--init` with `--run`. Use the actual board
port. In a second desktop terminal paste the **native UI command printed by the
launcher**. In a third terminal define the same DEMO/PY/RUN variables for markers.
Create/choose two test player profiles in the original Players UI, connect the
board and prepare a **Two players / 5 min / Guidance OFF** game. Arrange the real
standard position, Check position and verify types/colors. Do not press Start
until after the observation window begins.

The new launcher reuses the existing launcher's preflight, run lock, explicit
paths, original Server loop and cleanup. Only the demo Observer class is selected
in memory. DisplayClockObserver extends MoveObserver and observes original
GameSession operations, real monotonic tick values, native UI payloads and serial
failure paths. No production function, clock, UI or return value is replaced.
There is one serial owner and one native socket client, with no observer client.
The old launchers do not capture all required clock observations: legacy/missing
traces cause BLOCKED. No automatic setup, flashing or service management occurs.

## #27 TA scenarios

Keep a continuous recording of the **physical touchscreen and board**. Use a fresh
standard-position game for each scenario; End the preceding game normally and
restore physical pieces between windows. Keep the service running. Do not change
games within an open window.

### Names, turn, both clocks and accepted move

With a prepared, checked five-minute game, before pressing Start:

```sh
"$PY" -B "$DEMO/demo_27_display_updates.py" begin --run "$RUN" --window display-overview --case overview
```

1. Press Start in the native touchscreen UI. Show both actual player names,
   White to move, and both clocks. Wait briefly while White's clock decreases.
2. Physically play e2e4. Show Black to move and `e2e4` in the native last-move
   display; record the visible transition. Wait a few seconds on Black's turn too.
   Do not label backend data as pixels.
3. Open **View position**, then Previous/Next, to verify the accepted move/position
   history through existing UI controls. The active Game page renders the latest
   move, not a full move-list widget; the fixture adds no substitute widget.

```sh
"$PY" -B "$DEMO/demo_27_display_updates.py" end --run "$RUN" --window display-overview
```

The one-second checks cover players/turn/clocks at Start and turn/latest move at
acceptance. Existing View position supplies a separate functional history review.
If the TA requires a full live move-list widget, that capability is unavailable
and must be reported BLOCKED rather than synthesized.

### Check without mate

Prepare a new standard game and Start. Before moving:

```sh
"$PY" -B "$DEMO/demo_27_display_updates.py" begin --run "$RUN" --window display-check --case check
```

Physically play `e2e4 f7f6 d1h5`. The original rules identify **Check.** Show the
actual visible status; annotate the final accepted-move backend token.

```sh
"$PY" -B "$DEMO/demo_27_display_updates.py" end --run "$RUN" --window display-check
```

### Checkmate

Prepare and Start another standard game:

```sh
"$PY" -B "$DEMO/demo_27_display_updates.py" begin --run "$RUN" --window display-mate --case checkmate
```

Physically play Fool's Mate: `f2f3 e7e5 g2g4 d8h4`. Show the actual final
checkmate/result/status on the screen, then end this observation window (the
rules-completed game is allowed to be inactive):

```sh
"$PY" -B "$DEMO/demo_27_display_updates.py" end --run "$RUN" --window display-mate
```

### Blocking error survives unrelated updates

Start another fresh five-minute game:

```sh
"$PY" -B "$DEMO/demo_27_display_updates.py" begin --run "$RUN" --window display-error --case error
```

1. Physically attempt e2e5. Show Illegal move / restoration instruction.
2. Leave the board wrong while clocks and ordinary UI refreshes continue. Toggle
   the native **Guidance** control while on the active Game page. Record that this
   unrelated action does not clear the warning. Do not request a hint/network call.
3. Keep continuous video over this interval: isolated before/after screenshots do
   not prove persistence. Partial restoration must not count as resolved.
4. Restore the full accepted board, then show the warning clearing only after
   backend restoration. Return Guidance OFF for later clock tests.

```sh
"$PY" -B "$DEMO/demo_27_display_updates.py" end --run "$RUN" --window display-error
```

### Measure real visibility, or retain BLOCKED

Backend changes are captured as `dc_call` / `dc_return` records with matching
`token`, `operation`, raw state and monotonic nanoseconds. Their entry/return
interval bounds the actual backend update. `dc_state.payload` records what was
queued for the real UI, **not** when it became visible.

Use a high-speed camera or equivalent synchronized optical measurement of the
**final display**. Establish an actual conversion between recording timestamps
and the Pi's `time.monotonic_ns()` clock, with a documented uncertainty bound.
A valid method can use an externally timed optical marker or instrument that
records the display and a Pi-correlated timing signal. Include calibration before
and after the capture and account for frame/exposure bounds and drift. Do not
command board LEDs/motors or claim that a terminal timestamp became visible
instantaneously. Nominal FPS, unrelated wall clocks and a human stopwatch are not
a calibrated time-base conversion. This fixture does not assume equipment exists.

If such synchronization cannot be established, record functional observations
but leave `synchronized` false and timing bounds unavailable: timing is BLOCKED.
Do not derive screen timing from socket timestamps or copy backend timestamps
into visible-frame fields.

Attach each actual video using the existing tool; repeat with the four window
names. The attachment records its SHA-256:

```sh
"$PY" -B "$DEMO/record_evidence.py" --run "$RUN" --kind hardware --label display-overview --file /path/to/actual-video.mp4 --operator 'Your name' --note 'Final Pi 5/touchscreen/PCB; overview; calibration and visible frame references reviewed with TA'
```

Copy `display_visibility_example.json` into the test run (never overwrite source
or production data), and fill it using **actual** measurements. Its defaults are
deliberately incomplete and cannot pass. Use one document per window:

```sh
cp "$DEMO/display_visibility_example.json" "$RUN/overview-visibility.json"
# Edit this test-only copy with actual observations and calibrated bounds.
"$PY" -B "$DEMO/demo_27_display_updates.py" import-visibility --run "$RUN" --file "$RUN/overview-visibility.json"
```

Required document fields:

- `window`, actual observer `session`, reviewer and actual attached `video_sha256`.
- `measurement_kind: "physical_touchscreen"`, `timebase: "pi_monotonic_ns"`,
  `synchronized: true` only after calibration, `method`, measured `uncertainty_ns`.
- One `observations` object for each required token/field: `backend_token`, `field`,
  `correct` (true/false after review), actual `observed_text`, `visible_lower_ns`,
  `visible_upper_ns`, and a video `frame_reference`. For `clocks` also supply both
  strings in `displayed_clocks`, e.g. the **actually observed** `['05:00','05:00']`.

Fields to annotate: overview Start token → `players`, `turn`, `clocks`; overview
accepted-commit token → `turn`, `moves`; check and mate commit tokens → `status`;
illegal commit token → `error`; restoring on_board token → `error-cleared`.
Also annotate `clocks` for the first White-turn and Black-turn tick samples where
the active clock has decreased at least 1000 ms from its start value. These sample
tokens are printed in missing-evidence results. This selects visible remaining-time
updates; it does not introduce a clock-accuracy tolerance.

In the overview document add `history_review` with `correct`,
`native_view_position`, actual `moves` array and `frame_reference`. In the error
document add `persistence` with `rejection_token`, `restoration_token`,
`continuous_video_review`, `warning_persisted`, `cleared_after_restoration` and
actual `frame_range`. Missing review remains BLOCKED; an observed violation is FAIL.

Analysis expands visible bounds by the declared uncertainty. It passes timing
only if the **largest possible backend-to-visible delay is ≤1000 ms**, fails if
the smallest possible delay exceeds it, and otherwise reports BLOCKED. Every
sample retains endpoints, uncertainty, token, reviewer and video hash in results.
Attachments/annotations are operator evidence, not automatically authenticated
video content: the TA must inspect them.

## #28 TA clock workflow

Prepare a new standard **5 min PvP** game and verify the board. Before Start:

```sh
"$PY" -B "$DEMO/demo_28_clocks.py" begin --run "$RUN" --window clocks --case clock-workflow
```

1. Start; verify two five-minute clocks. Wait a few seconds on White's turn.
2. Physically accept e2e4. Wait a few seconds on Black's turn. Show that only the
   active clock decreases on each side.
3. Pause through the existing UI. Wait, show both frozen, then Resume and show no
   reset. Wait briefly for resumed running samples.
4. **Physically unplug the actual ESP32-S3 USB/UART communication cable** while
   keeping intended PCB power safe. Do not press UI Disconnect as a substitute.
   Record the unplug and actual fault detection/pause. Wait for frozen samples.
5. Reconnect the same hardware. Through normal application controls Connect,
   restore/verify the accepted board, resolve the physical cause and use Reset
   fault as required by the existing workflow. Show both clocks remain paused.
   Then explicitly Resume. No demo resets faults or resumes for the operator.
6. Wait for running samples; End through the native UI (End without result is
   acceptable). Keep the UI open a few seconds to show both clocks frozen.

```sh
"$PY" -B "$DEMO/demo_28_clocks.py" end --run "$RUN" --window clocks
"$PY" -B "$DEMO/record_evidence.py" --run "$RUN" --kind hardware --label clocks --file /path/to/actual-clock-video.mp4 --operator 'Your name' --note 'Final hardware; native pause/resume, physical cable unplug/replug, normal fault recovery and end; remaining times reviewed'
```

The observer records floating-point backend milliseconds and the original
rounded-millisecond API values separately; the native UI rounds these further
to displayed seconds. Equality/preservation checks use raw backend values, not
display text. No clock-accuracy tolerance is invented. Selftests use real
`time.monotonic`; no fake clock is supplied to production objects.

Each observed tick must decrease only the active side. Paused, disconnected and
ended ticks must preserve both exact raw values. Resume/reconnect must preserve
frozen values without reset. A genuine serial failure plus original I/O-dispatch
connection-loss path and physical video are required; a simulated connection API
call cannot pass.

Switch/pause/stop timing uses conservative accepted-event-to-effect bounds:
commit entry for a validated move; native UI handler entry for Pause/End; fault
latch entry for a detected communication fault. Function return bounds the effect.
The bound includes observation overhead. ≤500 ms proves the target; a larger
upper bound alone is inconclusive and BLOCKED, not a fabricated exact violation.
Definite incorrect clock behavior is FAIL. Physical-unplug→detection latency is
not inferred from backend logs or assigned a numeric deadline. If measured with
synchronized video, retain it separately from detection→pause. Otherwise the report
contains only the measured software detection and pause bounds, with the physical
unplug documented in reviewed video.

## Cleanup, reports and local checks

After closing all windows, finish active demo games normally, Quit the native
UI and Ctrl-C **this demo-owned service**. Existing cleanup clears LEDs, requests
STOP/STATUS through the same serial owner, closes resources and retains records.
Verify physical outputs safe; restore pieces manually. Do not kill/restart the
normal controller. Then evaluate:

```sh
"$PY" -B "$DEMO/demo_27_display_updates.py" evaluate --run "$RUN" --windows display-overview display-check display-mate display-error
"$PY" -B "$DEMO/demo_28_clocks.py" evaluate --run "$RUN" --windows clocks
```

Versioned `result-27/28-<timestamp>.json` files preserve per-assertion results,
backend raw values and measurement evidence. Raw calls/states are in
`events.jsonl`, boundaries/DB snapshots in `display_clock_windows.jsonl`, and
hashed imported annotations in `display_visibility.jsonl` plus `evidence/`.
Exit codes: 0 PASS, 1 FAIL, 2 BLOCKED, 130 interrupted. Empty/legacy traces,
synthetic observations and missing physical evidence cannot complete checkoff.

**Example only — not an executed hardware result:**

```text
TIDR #27: BLOCKED
  BLOCKED: display-overview: turn <=1000 ms — physical visibility timing unavailable
TIDR #28: BLOCKED
  PASS: clocks: only active clock decreases; clocks never reset/increase in ticks — ...
  BLOCKED: clocks: physical link failure, not UI Disconnect — ...
```

Local software checks, no hardware/service/UI launch:

```sh
python3 -B -m unittest discover -s tests/tidr_demos/selftests -v
git diff --exit-code
git diff --cached --exit-code
git status --short --untracked-files=all
```
