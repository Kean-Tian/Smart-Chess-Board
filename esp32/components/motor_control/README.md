# CoreXY motor control component

Shared C component for the final ESP32-S3 application and the current ESP32-S2
bench. It uses ESP-IDF's existing component build and a GPIO-write callback, with
no chip-specific pin numbers, dependencies beyond the C library, allocations,
tasks, interrupts or delays. The S2 harness is in [bench/corexy_s2](../../bench/corexy_s2/README.md).

## Existing project and integration boundary

The local application uses ESP-IDF, initializes GPIO/UART/RMT in
`main/app_main.c`, and runs `scb_core_tick` in a 1 ms FreeRTOS task. The core owns
the existing line protocol, motion watchdogs and electromagnet. Sensor/LED logic
lives in `components/board_logic`. Its existing motor routine is a bench-level,
independent X-then-Y pulse generator, not CoreXY kinematics.

The checked-out application targets LOLIN32/classic ESP32; remote commit
`8bdddda` targets ESP32-S2-Saola-1. The team confirmed that S2 is the current test
board and S3 is the intended final board. This addition does not migrate either
application or change any existing pin map. The **final S3 GPIO assignment and
mechanical calibration are still unconfirmed**.

The main component declares the new component as a dependency so it is available
to existing firmware. The current `app_main.c` and `scb_core.c` are unchanged;
their existing commands still use their original motion implementation. Use the
separate S2 bench to test this new module. Production command routing to CoreXY
must be enabled explicitly when the final board map and calibration are known.

## Calibration and coordinate convention

Callers must supply all of `ScbMotorConfig`, including both motor scales, the
signed mapping, Cartesian bounds, requested speed/acceleration, and task period.
Zero-initialized or incomplete calibration cannot enable the controller.

The mapping is:

```text
A_steps = A_steps_per_mm * (map[0][0] * X_mm + map[0][1] * Y_mm)
B_steps = B_steps_per_mm * (map[1][0] * X_mm + map[1][1] * Y_mm)
```

Every coefficient must be explicitly +1 or -1, with orthogonal rows. This covers
swapped motors and reversed DIR polarity without presuming which belt winding or
electrical direction the hardware uses. A means the driver labelled `X_STEP`,
B means the driver labelled `Y_STEP`; these are motor names, not independent
Cartesian axes. A familiar `A=X+Y, B=X-Y` is only one possible convention and is
used in simulation tests, not selected as a hardware default.

Steps/mm refer to the full steps actually emitted with MS1/MS2/MS3 grounded.
There is no assumed pulley pitch, tooth count, motor step angle, board square
size, current setting or working travel. Millimetre targets are rounded to the
nearest representable motor-step lattice relative to the manual reference.
`scb_motor_position` reports that quantized, open-loop position, not a sensor
measurement. Absolute targets avoid cumulative rounding drift.

## API and ownership

Include `scb/motor_control.h`. The public operations are:

| Function | Purpose |
|---|---|
| `scb_motor_init` | Validate configuration, set EN HIGH and STEP LOW; no motion |
| `scb_motor_enable` | Set shared active-low EN LOW; no STEP pulses |
| `scb_motor_reference` | Record a deliberately established manual X/Y reference |
| `scb_motor_move_to` | Plan a coordinated absolute move in millimetres |
| `scb_motor_move_motors` | Plan relative A/B motor steps, including either motor alone |
| `scb_motor_profile` | Change requested speed and acceleration while idle |
| `scb_motor_tick` | Advance a bounded pulse phase without waiting |
| `scb_motor_position` | Read the current emitted-step position in millimetres |
| `scb_motor_stop` | Disable both drivers, clear STEP and invalidate position |
| `scb_motor_result_name` | Convert a result code to text |

All calls belong to **one control-task owner**, including stop requests. In final
firmware, route the existing command parser/watchdogs through this owner instead
of letting the legacy pulse generator and this controller write the same pins.
Do not run two motion engines concurrently. Keep existing EM_CTRL logic in the
core: this module deliberately never controls the electromagnet. A board adapter
can construct `ScbMotorPins` directly from its verified `SCB_PIN_X_STEP`,
`SCB_PIN_X_DIR`, `SCB_PIN_Y_STEP`, `SCB_PIN_Y_DIR`, and `SCB_PIN_MOTOR_EN` macros.

The sequence is `init`, explicit `enable`, explicit manual `reference`,
`move_to`/`move_motors`, periodic `tick`, then `stop`. A reference can be supplied
while enabled and idle, after the rotor has settled. No homing operation is
invented. Both absolute and independent-motor moves require a reference.

At normal completion STEP is LOW and the drivers **remain enabled** to hold the
known position. Any disable, stop, clock reversal or output failure invalidates
it. The integrating application must maintain an arm/heartbeat interlock and
call stop on faults, stale links and shutdown. The S2 bench implements those
interlocks with the existing 2 s link / 30 s motion budgets.

## Pulse scheduling and limits

Integer DDA coordinates the two motors on the same major-event schedule. Each
event writes the selected STEP pins during the same tick, then a later tick
clears them. Paired writes are sequential GPIO calls, so actual inter-motor skew
requires a logic-analyzer measurement. DIR is set before scheduling the first
edge and stays fixed through the move.

The implementation requires at least 5 us for STEP HIGH, STEP LOW and DIR setup.
These are timing margins, not mechanical calibration. The [Allegro A4988
datasheet, page 6](https://www.allegromicro.com/~/media/files/datasheets/a4988-datasheet.pdf)
specifies 1 us STEP HIGH/LOW and 200 ns input setup/hold. Emergency stop disables
EN first and may truncate the final pulse; position is discarded.

A trapezoidal/triangular profile schedules acceleration and deceleration using
the coordinated Cartesian distance. The rate is capped at one major event per
two polling periods, at most 500 events/s with a 1 ms task. Polling quantizes
and stretches the profile; it is not a high-speed timer/DMA pulse engine. Delays
slow the move and never cause catch-up bursts. Each call performs constant
bounded work; it does not block sensing or LED work.

Requested endpoints, quantized endpoints and every proposed DDA event are
checked against configured Cartesian limits. An unrepresentable endpoint or
out-of-bounds intermediate step is rejected. Unequal motor scales can make DDA
cross a limit even with a legal endpoint; that move safely stops before the
violating event. Do not use a boundary as a substitute for a physical clearance
margin. Software numeric bounds also limit motor counts to +/-1 billion steps;
this is an arithmetic guard, not calibrated travel.

## Tests and changes to existing files

```sh
sh esp32/tests/run_core_tests.sh
cmake -S esp32/tests -B /tmp/scb-motor-host
cmake --build /tmp/scb-motor-host
ctest --test-dir /tmp/scb-motor-host --output-on-failure
```

Simulation covers all eight signed CoreXY mappings, unequal motor scales,
independent drivers, pulse edges and DIR setup, acceleration/deceleration,
delayed/backward clocks, invalid calibration, endpoint/intermediate limits,
GPIO failures, stop/reference invalidation, and the bench parser/watchdogs.
Test constants and test pin indices are synthetic, not hardware calibration.

Only these existing files are changed by the motor addition:

| File | Reason |
|---|---|
| `esp32/main/CMakeLists.txt` | Add `motor_control` to existing component dependencies |
| `esp32/tests/CMakeLists.txt` | Register the new host test executable with CTest |
| `esp32/tests/run_core_tests.sh` | Compile/run the new tests with the existing sanitizer setup |
| `esp32/README.md` | Link to the component and S2 bench instructions |

All implementation, S2 harness, calibration parser and motor tests are new files.
Existing application functions, GPIO assignments, protocol, sensor/LED code,
electromagnet code, Pi code and release images are unchanged by this addition.
Pre-existing uncommitted Pi/LED changes are separate from this work.

Validation on the development Mac: portable suites pass with undefined-behavior
sanitization; the root CMake build and all 11 CTest suites pass. This Mac needed
an explicit system C++ header search path in the temporary build configuration
(`-DCMAKE_CXX_FLAGS=-isystem /Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/c++/v1`);
no repository/compiler setup was changed. The local shell has no `idf.py` or activated ESP-IDF toolchain, so an
ESP32-S2/S3 firmware build, flashing, GPIO waveforms, motor directions, actual
travel, force/current/thermal behavior and the final S3 integration still need
validation in the hardware environment.
