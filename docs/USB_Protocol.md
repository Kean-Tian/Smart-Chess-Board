# MCU–Pi USB Protocol v1

The current MCU is **ESP32-S2-Saola-1**. The board's Micro-USB connector uses its USB-UART bridge, with UART0 TX=GPIO43 and RX=GPIO44, at 115200 baud, 8N1, without hardware flow control. GPIO1..8 are sensor inputs. Linux commonly uses `/dev/ttyUSB0`; macOS uses a detected `/dev/cu.usbserial-*` port. The Python client deasserts DTR/RTS before opening, waits 0.5 s, then checks PING.

## Framing

- ASCII lines end in LF; CRLF is accepted.
- `@42 STATUS` uses an optional nonnegative request ID, 0..2147483647. Omitting the prefix uses ID 0. The Python client supplies IDs to match concurrent replies.
- Requests have a maximum of 127 bytes before LF. Overflow or invalid control bytes cause the complete line to be discarded through LF.
- Replies include `ACK 42 COMMAND`, `ERR 42 REASON`, `DONE 42 MOTION` and `STATUS 42 armed=0 moving=0 magnet=0 origin=0 steps=0 polarity=HIGH`.
- Boot identifier: `HELLO SCB_S2_SAOLA_1 1`. It is sent once and may be missed when opening later.
- Unsolicited messages include BOARD, SENSOR, EVENT and FAULT.
- BOARD/RAW masks contain exactly 16 hexadecimal digits, with bit0=a1, bit7=h1 and bit63=h8. These are logical coordinates; physical board orientation is not yet calibrated.
- Under TX backpressure, only complete lines are dropped. A command may then time out. Motion requests must not be automatically replayed.

## Sensor Messages and Display

```text
BOARD 0000000000000080
SENSOR frame=2 mux=000 A0=36:0 A1=37:0 A2=38:0 inputs=00000001 occupy=0000000000000080 polarity=HIGH
```

The Python terminal renders these as:

```text
BOARD | OCCUPY=h1
MUX(A2,A1,A0)=000 [GPIO36,37,38=000] | INPUTS(DIG_OUT1..8)=00000001 | OCCUPY=h1 | frame=2
```

- `mux` is A2,A1,A0; the bracketed GPIO levels are A0,A1,A2. Address 001 therefore has GPIO36,37,38 = 100.
- `inputs` contains the captured raw electrical levels in DIG_OUT1..8 order. Its leftmost character is DIG_OUT1, not DIG_OUT8.
- `occupy` is the whole debounced board, not just this row. Raw inputs, row address and occupancy belong to the same accepted frame.
- HIGH currently means occupied. Empty/full terminal masks display `无棋子` / `全部64格`; the transmitted masks remain hexadecimal.
- Automatic SENSOR reports cover occupied rows after board changes and are coalesced to at most five snapshots per second, with up to eight row lines per snapshot. This is a debug-output limit, not a 5 Hz scan rate. SCAN forces an immediate snapshot of the latest stable occupied rows. An empty board produces BOARD zero without occupied-row SENSOR lines.
- `frame` identifies the accepted scan frame. It is not a square number. A logical `h1` result does not by itself mean physical top-right; the user observed it at physical lower-left. See the orientation procedure in the test guide.

## Commands

| Request | Behavior |
|---|---|
| `PING` | Refresh the heartbeat; other commands do not refresh it |
| `STATUS` | Armed/moving/magnet state, manual origin, steps per square and polarity |
| `INPUTS` | Instantaneous GPIO1..8 electrical levels, in DIG_OUT order; not a full scan or necessarily the row in the last SENSOR report |
| `SCAN` | Report the latest stable whole BOARD and occupied-row SENSOR snapshot, then ACK; NOT_READY until a stable frame exists |
| `RAW` | Report the most recent complete, polarity-normalized pre-debounce RAW board, then ACK; also requires the initial stable frame |
| `TIMING` | Complete-frame count, last/maximum interval, intervals >=20 ms and candidate-to-accept debounce time, in microseconds |
| `PLATFORM` | LED queue-to-RMT-completion timing, >=100 ms counts/failures and free/minimum internal heap |
| `POLARITY HIGH` / `LOW` | Select occupied input level; reset debounce, move baseline and scan timing counters |
| `LED e4 0 20 0` | Set an external RGB square; accept 0..255 and cap actual channels at 32; preserve other pixels |
| `LED_CLEAR` | Clear all external RGB pixels |
| `MARK e2 e4 LEGAL` | Clear pixels; source blue and destination green |
| `MARK e2 e5 ILLEGAL` | Clear pixels; source and destination red |
| `SET_STEPS n` | Set 1..2000 steps per square and invalidate the old origin; no assumed calibration |
| `ORIGIN a1` | Record manual alignment without moving |
| `ARM` | Enable actuator commands after a fresh PING |
| `STOP` / `DISARM` | Abort motion, release magnet, disable motors and invalidate origin; scanning and reports continue |
| `GOTO e2` | Move to a square with magnet off; requires ARM, calibration and origin |
| `MOVE e2 e4` | Require alignment at e2, energize magnet, wait, move X then Y and release |
| `JOG X 20` / `JOG Y -20` | Bench relative steps, magnitude 1..1000; requires ARM, invalidates origin |
| `MAGNET ON` / `OFF` | Manual magnet control; ON requires ARM; cannot override during movement |
| `HOME` | Return NO_HOME_SWITCHES; no automatic homing is implemented |

MOVE/GOTO/JOG return ACK id MOTION and later DONE id MOTION or ERR id reason. DONE confirms commanded pulses, not successful physical transport. Compare BOARD separately.

## Timing and Fault Handling

The Python client sends PING every 0.5 s. The MCU disables actuators after 2 s without PING while armed or active. Magnet ON is limited to 5 s and motion to 30 s. Repeated ON does not extend continuous energization. The default step schedule is approximately 100 steps/s per active axis, X then Y; delays reduce rate without catch-up bursts. LED output failure also shuts down actuators.

A 1 ms control task schedules nominal 10 ms complete-board frames with 1 ms row settling and two matching frames for debounce. The S2 has one CPU: control priority 10, serial 4, LED 3. RMT uses interrupt refilling without DMA. LED ACK means queued, not illuminated. PLATFORM does not measure optical latency. See [specification alignment](Specification_Alignment.md).

Motion-time occupancy is telemetry, not a human move; the move baseline is re-established afterward. EVENT MOVE is a candidate, not proof of legality. Multiple simultaneous changes can produce AMBIGUOUS. The Pi rules layer validates moves and compares occupancy. Recovery requires restoring the physical board when a move is rejected.

## Python Clients

`pi5/app/scb_link.py` owns the serial reader, request matching, event queue and heartbeat. Its terminal drains events while waiting for keyboard input; no Enter key is required to show sensor changes. Request timeout sends STOP and raises an error without retrying motion. `quit`/Ctrl-C closes the client and sends STOP. This does not mute firmware scanning; close the terminal to stop its display, and remove power to stop all MCU activity.

`pi5/app/board_game.py` handles rules and physical synchronization. Board mode can indicate computer moves through external LEDs and asks for manual execution; it does not automatically ARM or move motors. Promotions or ambiguous changes can use `commit <uci>` with matching occupancy. Motor path planning, automatic captures and homing are not implemented.

## Initial Sensor Test

From the project root:

```sh
esp32/.venv/bin/python pi5/app/scb_link.py --port PORT
```

Enter PING, STATUS, SCAN, RAW, INPUTS and TIMING. Keep actuator power disconnected. Use [the S2 test guide](ESP32_S2_Test_Guide.md) before LED or motion testing; no universal steps-per-square calibration is supplied.
