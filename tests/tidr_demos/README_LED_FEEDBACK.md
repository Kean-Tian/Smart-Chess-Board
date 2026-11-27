# TIDR #37/#38/#39 — final-hardware LED feedback

Only new demo files are added. No earlier demo, firmware, LED driver, native UI,
configuration, database schema or production entry point is changed. Hardware
execution is **manual only**. No hardware verification result accompanies this
implementation.

`GameSession.feedback_command` is an existing **string attribute**, not a callable.
The original `UiCore.feedback_update()` consumes it and uses its existing worker
to send GUIDE/MARK/LED_CLEAR. LedObserver extends the shared observers to record
that input, actual worker-origin command attempts, ACK/PLATFORM frames if received,
and transaction-return anchors. It never sends commands from an observation hook.
The new launcher calls the existing shared demo launcher unchanged, selecting
only a demo observer class in memory. Original game decisions remain authoritative.

## 1. Manual all-64 mapping characterization, before the UI owns hardware

Use final Pi 5, touchscreen, ESP32-S3 PCB, Hall board, magnetic pieces and WS2812B
array. Verify intended PCB power (USB alone does not supply the master PCB).
Safely close the normal controller **yourself**, plus all serial terminals. Never
run the mapping capture alongside the UI/service. From the repository root:

```sh
DEMO="$PWD/tests/tidr_demos"
PY="$PWD/pi5/.venv/bin/python"
RUN="$DEMO/runs/led-feedback"

"$PY" -B "$DEMO/preflight.py" --init "$RUN" --purpose records --port /dev/ttyACM0
"$PY" -B "$DEMO/verify_led_mapping.py" --run "$RUN" --port /dev/ttyACM0 --operator 'Your name' --operator-confirms-controller-stopped
```

Use the actual device. For an existing isolated run use preflight `--run`, not
`--init`. Missing prerequisites, occupied/uncertain ownership, unsupported fresh
snapshots or unsafe MCU outputs cause BLOCKED. No service is stopped for you.
The capture requires an interactive terminal and explicit acknowledgment.

Remove all pieces. Record the entire mapping run. For every labelled physical
square a1 through h8, the tool calls existing `ScbLink` commands to illuminate one
dim blue LED. Inspect the **whole array**, type `ONLY a1` (etc.) only if exactly
that labelled physical square alone illuminates, place one real piece there,
and remove it when prompted. Original fresh SNAPSHOT must report precisely its
one logical bit and then zero. No polarity/orientation patch or masking is applied.
The test identifies incorrect physical mapping; it does not repair it. Firmware
coordinates and the diagnostic UI's display coordinates must not be conflated.

This is separate characterization using the supported exclusive interface; the
actual #37–#39 game demos never use its manual LED commands. On completion/error/
Ctrl-C it attempts LED_CLEAR, STOP and STATUS through its own link, then closes it.
STOP invalidates declared carriage origin. Verify actual LEDs dark, motors/magnet
off; a software ACK is not proof of physical safety. Fault latches are preserved.

The tool prints a **Mapping ID** and retains `led_mapping.jsonl`. Its initial
aggregate remains BLOCKED for independent video review. Attach the actual reviewed
recording with the exact ID (replace MAPPING_ID, do not type it literally):

```sh
"$PY" -B "$DEMO/record_evidence.py" --run "$RUN" --kind hardware --label mapping-MAPPING_ID --file /path/to/actual-mapping-video.mp4 --operator 'Your name' --note 'Mapping ID MAPPING_ID; final physical labels, all 64 sensor bits and only named LEDs verified with TA'
```

All 64 correct records, acknowledged cleanup and matching reviewed evidence are
required before a game-demo window can begin. An incomplete/failed/synthetic map
blocks dependent demonstrations. Do not substitute development hardware or an old
recording from a differently assembled board. Repeat mapping after wiring changes.

## 2. One service launch for the combined workflow

After the mapping tool releases the device, manually launch:

```sh
"$PY" -B "$DEMO/run_led_service.py" --run "$RUN" --port /dev/ttyACM0 --operator-confirms-controller-stopped
```

In a second desktop terminal paste its printed native UI command. Do not run
`pi5/start.sh ui` or another launcher alongside it. The native UI is the only
socket client and its original service is the only serial owner. The shared
launcher forces automatic motion off. No ARM/GOTO/MOVE/JOG/MAGNET commands are
part of these demos; actuator telemetry must remain safely idle.

Create/select two test profiles using the existing Players page. Prepare
**Two players / No clock**, arrange the real standard board, Check position,
verify physical types/colors, Start. Enable Guidance using the native UI. In a
third terminal define DEMO/PY/RUN as above. Begin #37 and #38 together:

```sh
"$PY" -B "$DEMO/demo_37_guidance_leds.py" begin --run "$RUN" --window led-guidance
"$PY" -B "$DEMO/demo_38_accepted_leds.py" begin --run "$RUN" --window led-accepted
```

The scripts only record observation boundaries/isolated DB snapshots. They do
not manipulate the board, inject events, open another connection or produce LED
patterns themselves. Start video before physical actions and keep the entire
array in view. Each token/result remains independently associated with its TIDR.

## 3. Combined physical TA sequence

### #37 guidance, followed by the first #38 accepted move

1. Physically lift e2. Verify **only e3/e4 green**, with no source or extra LEDs.
   Hold long enough to record actual illumination. Return e2; observe all dark.
2. Lift g1. Verify **only f3/h3 green**. Return it; observe all dark.
3. Lift a1, the blocked rook. Verify **no LEDs**. Return it; remain dark. An empty
   legal set is a real case, not missing sensor data.
4. Lift e2 again and record its guidance, then physically complete e2e4. Observe
   old guidance removed and **e2 blue / e4 green** as accepted feedback.

Every lift must be backed by the actual ESP sensor event and original rule-engine
legal list. This includes the second e2 lift. No mocked piece movement is accepted.

```sh
"$PY" -B "$DEMO/demo_37_guidance_leds.py" end --run "$RUN" --window led-guidance
```

### Finish #38 in the same application session

5. Physically play e7e5. Verify **e7 blue / e5 green**, with e2/e4 and every other
   square off. Record actual light onset for both accepted moves, not their ACKs.
6. On White's turn physically attempt g1g3 (illegal knight move). Compare actual
   **red g1/g3** with the accepted blue/green pattern. Restore g1 fully.
7. End this game through the existing UI (End without result is sufficient for
   this fixture). Observe all LEDs dark. Prepare a new PvP/No clock game and
   verify no old indication remains. Prepare does not need to retransmit a clear
   if the array is already dark; the physical condition still must be observed.

```sh
"$PY" -B "$DEMO/demo_38_accepted_leds.py" end --run "$RUN" --window led-accepted
```

This #38 fixture covers the requested two nonterminal accepted moves and manual
End/preparation. The current production rules-completion branch selects LED_CLEAR
immediately. It does not establish a separate final checkmating-move indication;
if that is required by the TA, report the limitation rather than adding a flash.

### #39 rejected warning and complete restoration

Restore the physical standard board, Check/verify/Start the prepared new game.
Guidance may be off. Keep the service running; no restart is necessary:

```sh
"$PY" -B "$DEMO/demo_39_rejected_leds.py" begin --run "$RUN" --window led-rejected
```

8. Physically attempt e2e5. Show actual rejection and **red e2/e5** only.
9. Leave the board wrong and verify the warning persists. Attempt d2d4 and/or
   toggle Guidance in the existing UI. Verify the warning is not replaced/cleared.
10. Return the e5 pawn to e2 **while d2 remains on d4**. This is partial restoration:
    verify original red e2/e5 warning still holds despite neither square now
    identifying the remaining mismatch. The warning describes the rejected move.
11. Return d4 to d2. Wait for actual full-board restoration confirmation and then
    verify red warning clears. Record continuous optical evidence over the whole
    hold/unrelated-action/partial/full sequence. Endpoint screenshots cannot prove
    continuity. **Never manually issue LED_CLEAR to simulate success.**

```sh
"$PY" -B "$DEMO/demo_39_rejected_leds.py" end --run "$RUN" --window led-rejected
```

#39 has no numeric deadline. Its assertions cover colors/coordinates, unchanged
accepted records, no early clear/replacement command, partial restoration and
continuous warning until the original system confirms full restoration.

## 4. Optical evidence and actual latency

The logs distinguish four different observations:

| Record | What it establishes |
|---|---|
| `led_input` | Original feedback controller observed its desired pattern |
| `led_command` / `led_transport` ACK | Command attempted through original worker / firmware accepted it |
| PLATFORM, if independently available | Firmware queue-to-RMT-completion diagnostic, not optical onset |
| Imported actual optical frames/samples | Physical illumination and full-array pattern |

ACK or RMT completion **never** passes a physical 500 ms assertion. The observer
does not send extra PLATFORM requests: its absence is unmeasured diagnostics, not
a fabricated zero. Native gameplay uses the original supported service interface.

For #37, the legal-destination receiving boundary is bounded by the LIFT handler
entry (before destinations exist) and the first original feedback_update input
observation. Using the earlier bound for acceptance conservatively includes
generation and queue delay rather than starting late at an ACK.

For #38, `led_store_return` samples original GameStore.move return **after its
transaction exits and before the accepted game swap/feedback assignment**. Only
a subsequent successful commit and matching separately read DB snapshot validate
this anchor. The accepted-event bracket ends at commit return. An exceptional
store return cannot by itself establish successful persistence.

Use synchronized high-speed video or a photodetector/instrument capture. Establish
an actual conversion to the Pi monotonic nanosecond time base, with documented
frame/exposure bounds, drift and measurement uncertainty, ideally calibrated
before and after recording. A photodetector can time onset at a square but cannot
alone verify all 64 colors/absence of extras: also retain wide-view video or full
array inspection. Include coordinates, physical board labels and reference frame/
instrument sample IDs. Do not equate terminal print, wall time, nominal FPS,
command-send time or a human stopwatch with calibrated optical onset.

If the equipment cannot establish this timing, retain functional observations
but leave synchronization false/bounds unknown: #37/#38 timing is BLOCKED. If
the largest possible latency is ≤500 ms it passes; if the smallest possible is
>500 ms it fails; overlapping uncertainty remains BLOCKED. The blocked rook has
no light-on edge: document the all-dark observation after receiving its empty set.
Return, completion and preparation clearing have no invented latency threshold.

Attach actual evidence independently for each window. The same recording can
cover several windows, but use each window label and identify its segment:

```sh
"$PY" -B "$DEMO/record_evidence.py" --run "$RUN" --kind hardware --label led-guidance --file /path/to/actual-video.mp4 --operator 'Your name' --note 'Final hardware; #37 segment, full array, calibrated optical references'
"$PY" -B "$DEMO/record_evidence.py" --run "$RUN" --kind hardware --label led-accepted --file /path/to/actual-video.mp4 --operator 'Your name' --note 'Final hardware; accepted/illegal contrast, replacement, End and preparation'
"$PY" -B "$DEMO/record_evidence.py" --run "$RUN" --kind hardware --label led-rejected --file /path/to/actual-video.mp4 --operator 'Your name' --note 'Final hardware; continuous warning through unrelated action, partial and full restoration'
```

Create test-only annotation copies of `led_optical_example.json`, one per window.
Get actual session/tokens from `events.jsonl` and actual SHA-256 from the matching
`attachments.jsonl` entry. Missing-evidence result details also list needed tokens.
The template's defaults cannot pass. It uses:

- `measurement_kind: physical_leds`, window/session/reviewer/method and actual
  `evidence_sha256`, binding observations to an existing hashed attachment.
- `synchronized: true` only after real calibration, `timebase: pi_monotonic_ns`,
  measured `uncertainty_ns` for timed observations.
- Each observation has `role`, actual `anchor_token`, `all_64_inspected: true`,
  `frame_reference` and `lit`: a map of **every observed lit square to its actual
  color**, e.g. `{"e2":"blue","e4":"green"}`. The complement is explicitly
  reviewed as off. Empty map means inspected and all dark; null means unknown.
  Do not omit a wrong/additional LED to make the map match.
- Timed observations additionally need actual `optical_lower_ns` and
  `optical_upper_ns` bounds on onset/empty-set observation in the calibrated clock.

Required roles/anchors:

| TIDR | Role | Anchor token |
|---|---|---|
| #37 | `guidance` for each lift, including repeated e2 | `mv_call GameSession.event` LIFT token |
| #37 | `return` for e2/g1/a1 | `dc_call GameSession.on_board` that clears legal_source |
| #37 | `move-complete` | accepted `dc_call GameSession.commit` e2e4 token |
| #38 | `accepted` for e2e4/e7e5 | each accepted `dc_call GameSession.commit` token |
| #38 | `illegal-comparison` | rejected g1g3 commit token |
| #38 | `end`, `prepare` | respective `dc_call GameSession.end` / `prepare` tokens |
| #39 | `rejected` | rejected e2e5 commit token |
| #39 | `partial` for each distinct partial-restoration mask | its first `dc_call GameSession.on_board` token |
| #39 | `restored` | full-restoration on_board token |

For #39 also add a `persistence` object with actual `rejection_token`,
`restoration_token`, `frame_range`, and reviewed true/false values for
`continuous_video_review`, `no_warning_gap`, `warning_until_confirmation`,
`unrelated_actions_covered`, `partial_restoration_covered`,
`cleared_only_after_restoration`. Unknown flags remain absent/null and BLOCKED.
False observed behavior is FAIL. The TA must review the footage: hashes establish
integrity, not automatic truth of video annotations.

```sh
cp "$DEMO/led_optical_example.json" "$RUN/guidance-optical.json"
# Fill this test-only file with actual evidence. Also prepare accepted-optical.json
# and rejected-optical.json, with their own window names, tokens and observations.
"$PY" -B "$DEMO/demo_37_guidance_leds.py" import-optical --run "$RUN" --file "$RUN/guidance-optical.json"
"$PY" -B "$DEMO/demo_38_accepted_leds.py" import-optical --run "$RUN" --file "$RUN/accepted-optical.json"
"$PY" -B "$DEMO/demo_39_rejected_leds.py" import-optical --run "$RUN" --file "$RUN/rejected-optical.json"
```

## 5. Cleanup and independent results

After all three windows close, End the active demo game normally, Quit the UI,
then Ctrl-C **the demo-owned service terminal**. Original shared cleanup attempts
LED_CLEAR, STOP and safe STATUS through the same link, waits for its workers and
closes serial/socket/DB resources. No normal service is killed/restarted. Verify
actual darkness and safe motor/magnet outputs; unacknowledged cleanup is reported
and requires manual safe-state inspection. Restore pieces manually and retain
all test games/evidence. Cleanup commands must remain outside observation windows.

After clean shutdown, evaluate independently:

```sh
"$PY" -B "$DEMO/demo_37_guidance_leds.py" evaluate --run "$RUN" --windows led-guidance
"$PY" -B "$DEMO/demo_38_accepted_leds.py" evaluate --run "$RUN" --windows led-accepted
"$PY" -B "$DEMO/demo_39_rejected_leds.py" evaluate --run "$RUN" --windows led-rejected
```

Results are versioned `result-37/38/39-<timestamp>.json`; raw inputs/commands/ACKs,
timestamps and states are in `events.jsonl`. Window boundaries and DB snapshots
reuse `display_clock_windows.jsonl`; imported optical documents are hashed in
`led_optical.jsonl` plus `evidence/`. #37/#38 retain actual start/end bounds,
uncertainty and calculated latency intervals. Independent assertions remain
separate even though footage/events are shared.

Exit codes: 0 PASS, 1 FAIL, 2 BLOCKED, 130 interrupted. Missing mapping, optical
frames, timing calibration, real sensor dispatch, safe telemetry or complete
observer logs cannot produce a hardware PASS. No mocked response is physical proof.

**Example only — not an executed hardware result:**

```text
TIDR #37: BLOCKED
  BLOCKED: led-guidance: optical guidance <=500 ms — physical timing evidence unavailable
TIDR #38: BLOCKED
  PASS: led-accepted: successful persistence precedes accepted LED feedback — ...
  BLOCKED: led-accepted: optical accepted — ...
TIDR #39: BLOCKED
  BLOCKED: led-rejected: continuous physical warning until confirmed restoration — ...
```

Local software validation (no serial/UI/service/hardware launch):

```sh
python3 -B -m unittest discover -s tests/tidr_demos/selftests -v
git diff --exit-code
git diff --cached --exit-code
git status --short --untracked-files=all
```
