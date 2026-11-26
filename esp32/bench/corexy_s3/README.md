# SCB Master PCB V3 CoreXY Bench — ESP32-S3

Standalone S3 test firmware using the same GPIO header and native USB/J6 UART transport as the main firmware. Flashing it replaces the chess application. It does not run chess sensing/UI/LED feedback and keeps EM_CTRL LOW. Restore the normal release after the bench test.

The V3 schematic and PCB agree: X STEP=35/DIR=34 and Y STEP=37/DIR=36. The obsolete V2 motor-routing option has been removed. GPIO46 drives D6 HIGH after application startup for the requested PCB test; reset/boot strapping levels are not controlled by the application. Physical actuator accuracy remains unverified.

Build from a new ESP-IDF 5.5.3 S3 build directory:

```sh
idf.py -C esp32/bench/corexy_s3 -B build-s3 set-target esp32s3
idf.py -C esp32/bench/corexy_s3 -B build-s3 menuconfig
idf.py -C esp32/bench/corexy_s3 -B build-s3 build
idf.py -C esp32/bench/corexy_s3 -B build-s3 -p ACTUAL_PORT flash
python3 pi5/app/scb_link.py --port ACTUAL_PORT
```

J5 requires external board power. Native USB is the default, typically ttyACM0/cu.usbmodem; optional J6 UART1 is TX17/RX18 at 115200 8N1. Close other serial clients. HELLO is `SCB_COREXY_S3_BENCH 1`. The ScbLink console supplies heartbeat and STOP on exit. Verify hardware driver current, rails, full-step mode and clearance before enabling any motor. Hardware-test results are not established by a successful build.

## Explicit configuration, no calibration defaults

All calibration is volatile and lost on reboot. No motion runs at boot.
`ARM` fails until **all four** configuration commands have been accepted:

| Bench command | Meaning |
|---|---|
| `MAP ax ay bx by` | Explicit +/-1 mapping coefficients, including motor order/DIR polarity |
| `SCALE a b` | Measured full steps/mm for motor A and motor B |
| `LIMITS xmin xmax ymin ymax` | Verified Cartesian travel in mm, with clearance |
| `PROFILE speed acceleration` | Requested positive mm/s and mm/s2 |
| `PING` | Refresh 2 s arm/hold watchdog |
| `ARM` | Validate full configuration and enable coils; does not step |
| `ORIGIN x y` | Record the physically established manual position in mm |
| `GOTO x y` | Coordinated absolute move in mm |
| `JOG A n` / `JOG B n` | Relative signed full steps, +/-1..1000, one driver only |
| `POSITION` | Report quantized emitted-step Cartesian position |
| `STATUS` | Report arm/motion/reference/config/fault state |
| `STOP` / `DISARM` | Immediate disable; clear reference and stop any pending motion |

Calibration changes require STOP first. `STATUS config=15` means all four
groups were supplied; ARM still validates their combined configuration. Neither
ARM nor ORIGIN can compensate for unknown mechanics. ORIGIN is a declaration
that you physically aligned the carriage; it does not find an origin or limit.
There is no HOME command because limit-switch wiring has not been confirmed.

The sequence below is a **parameter template**, not executable calibration.
Replace every angle-bracket placeholder with verified values; this document
deliberately supplies no presumed motor directions, steps/mm or travel:

```text
STOP
MAP <ax> <ay> <bx> <by>
SCALE <a_steps_per_mm> <b_steps_per_mm>
LIMITS <xmin> <xmax> <ymin> <ymax>
PROFILE <speed_mm_s> <acceleration_mm_s2>
ARM
ORIGIN <manually_aligned_x_mm> <manually_aligned_y_mm>
GOTO <nearby_verified_x_mm> <nearby_verified_y_mm>
POSITION
STOP
```

Keep the client heartbeat active for ARM and throughout enabled hold. After a
successful move the coils stay enabled, preserving the reference for the next
move. STOP, a 2 s heartbeat lapse, a 30 s move timeout or a GPIO fault disables
the drivers and invalidates position. Re-establish physical alignment after
every disable. GPIO faults are reported after attempting EN HIGH and both STEP
LOW; software cannot guarantee a physical output if hardware writes fail.

The bench accepts the existing `@request_id` framing and ACK/ERR/DONE replies.
Its **motion arguments differ from chess firmware**: GOTO uses numeric mm,
and JOG uses A/B motor names. This is a separate test application; the normal
firmware's commands are unchanged. DONE confirms emitted pulses only.

## Hardware verification order

1. With motor power off, check startup EN HIGH, both STEP LOW and EM_CTRL LOW.
   Verify ARM is rejected before configuration and no STEP occurs from ARM alone.
2. Confirm the schematic/jumpers and measured full-step/DIR behavior. Use only
   verified conservative test parameters. If physical mapping/scale is unknown,
   establish it externally before enabling this referenced-movement harness.
3. Use a logic analyzer to check DIR setup, STEP HIGH/LOW, and A/B pulse counts
   and skew. Start with a short referenced move away from all boundaries.
4. Check A-only and B-only operation (each moves both Cartesian coordinates),
   then pure X, pure Y, diagonals, return moves and the measured position scale.
5. Verify STOP during travel, client exit, heartbeat loss, movement timeout and
   rejected software limits. Confirm no motion resumes without explicit ARM and
   a newly established reference.

The component uses a polled 1 ms task and caps major events at 500/s; task
jitter lowers speed. This test does not validate homing, obstacle avoidance,
automatic captures, missed-step detection, chess integration or electromagnet
transport. It is not a firmware image for the final S3 pinout.

## Host simulation

```sh
sh esp32/tests/run_core_tests.sh
```

This compiles and exercises the shared component and the actual bench parser
with simulated GPIO, alongside the existing firmware-core regression tests.
Target firmware compilation requires ESP-IDF; there is no target-compiled or
hardware-validated S3 image included in this addition.
