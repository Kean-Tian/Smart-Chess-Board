# ESP32-S2 CoreXY motor bench

Standalone ESP-IDF application for the team's current ESP32-S2-Saola-1 test
board. It uses the same [shared motor component](../../components/motor_control/README.md)
intended for final ESP32-S3 integration. It has its own build directory and does
not change the existing chess firmware's tasks, UART protocol, LEDs or sensors.
Flashing this bench replaces the application on the test S2; keep a separately
verified normal S2 firmware available to restore afterwards.

## Recorded S2 harness

These are copied from remote commit
[`8bdddda`](https://github.com/Kean-Tian/Smart-Chess-Board/blob/8bdddda0641941a8b874d10a5b7bba080d39f451/esp32/main/board_pins.h),
not inferred from the local LOLIN32 configuration or final S3 PCB.
Confirm the actual jumpers match before attaching drivers.

| Signal | S2 GPIO |
|---|---:|
| A / X_STEP | 14 |
| A / X_DIR | 21 |
| B / Y_STEP | 15 |
| B / Y_DIR | 16 |
| MOTOR_EN, shared active LOW | 13 |
| EM_CTRL, held OFF throughout this test | 12 |
| USB-UART TX / RX | 43 / 44 |

Maintain the hardware EN pull-up, 3.3 V driver logic, common ground, appropriate
separate motor supply and mechanically verified driver current limit. Software
does not alter MS1/MS2/MS3 or the A4988 current limit. SLEEP/RESET must already be
wired for operation; this test assigns no GPIO to them. Sensor/LED pins are not
configured. EM_CTRL is held LOW, so this tests the carriage without carrying a
piece. Normal firmware remains responsible for electromagnet control.

## Build and connect

Activate the project's ESP-IDF 5.5.3 environment. From the repository root:

```sh
idf.py -C esp32/bench/corexy_s2 set-target esp32s2
idf.py -C esp32/bench/corexy_s2 build
```

With actuator power disabled during flashing, use the test S2's actual port:

```sh
idf.py -C esp32/bench/corexy_s2 -p /dev/cu.usbserial-XXXX flash
python3 pi5/app/scb_link.py --port /dev/cu.usbserial-XXXX
```

The existing `ScbLink` terminal supplies PING every 0.5 s and sends STOP on exit
or a timed-out GOTO/JOG request. Its opening banner mentions normal chess
commands; use **only the bench commands below** with this firmware. A plain
serial terminal must supply its own periodic PING. HELLO identifies
`SCB_COREXY_S2_BENCH 1`. UART is 115200 8N1, through the onboard USB-UART bridge.

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
hardware-validated S2 image included in this addition.
