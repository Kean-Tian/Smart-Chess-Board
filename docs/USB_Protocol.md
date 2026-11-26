# MCU–Pi USB Protocol v1

The current MCU is **SCB Master PCB V3 (bare ESP32-S3)**. J5 USB-B is directly wired to native USB Serial/JTAG on GPIO19/20, not a CP210x bridge. J5 VBUS connects to ESD protection and a capacitor, not the system power rail, so external PCB power is required. Default USB device names are `/dev/ttyACM0` on Pi and a detected `/dev/cu.usbmodem*` on macOS. A wired-UART firmware option uses J6 TX17/RX18 (UART1) at 115200 8N1; ROM UART0 pins43/44 are unconnected. USB and UART are mutually exclusive application transports selected at build time. The same line protocol is retained. See [PCB connection map](PCB_Connection_Map.md).

## Framing

- ASCII lines end in LF; CRLF is accepted.
- `@42 STATUS` uses an optional nonnegative request ID, 0..2147483647. Omitting the prefix uses ID 0. The Python client supplies IDs to match concurrent replies.
- Requests have a maximum of 127 bytes before LF. Overflow or invalid control bytes cause the complete line to be discarded through LF.
- Replies include `ACK 42 COMMAND`, `ERR 42 REASON`, `DONE 42 MOTION` and `STATUS 42 armed=0 moving=0 magnet=0 origin=0 steps=0 polarity=HIGH`.
- Boot identifier: `HELLO SCB_MASTER_PCB_V3_S3 1`. It is sent once and may be missed when opening later.
- Unsolicited messages include BOARD, SENSOR, EVENT and FAULT.
- BOARD/RAW masks contain exactly 16 hexadecimal digits, with bit0=a1, bit7=h1 and bit63=h8. These are logical coordinates; physical board orientation is not yet calibrated.
- Under TX backpressure, only complete lines are dropped. A command may then time out. Motion requests must not be automatically replayed.

## Sensor Messages and Display

```text
BOARD 0000000000000080
SENSOR frame=2 mux=000 A0=6:0 A1=5:0 A2=4:0 inputs=00000001 occupy=0000000000000080 polarity=HIGH
```

The Python terminal renders these as:

```text
BOARD | OCCUPY=h1
MUX(A2,A1,A0)=000 [GPIO10,9,8=000] | INPUTS(DIG_OUT1..8)=00000001 | OCCUPY=h1 | frame=2
```

- `mux` is A2,A1,A0; the bracketed GPIO levels are A0,A1,A2. Address 001 therefore has GPIO10,9,8 = 100.
- `inputs` contains the captured raw electrical levels in DIG_OUT1..8 order. Its leftmost character is DIG_OUT1, not DIG_OUT8.
- `occupy` is the whole debounced board, not just this row. Raw inputs, row address and occupancy belong to the same accepted frame.
- HIGH currently means occupied. Empty/full terminal masks display `Empty` / `All 64 squares`; the transmitted masks remain hexadecimal.
- Automatic SENSOR reports include occupied and changed rows, including the row where the last magnet was removed. They are coalesced to at most five snapshots per second, with up to eight row lines per snapshot. This limits debug traffic, not the nominal 100 Hz full-board scanning schedule. SCAN bypasses the trace throttle and reports all eight rows from the latest accepted snapshot, including empty rows. INPUTS shows captured electrical levels; OCCUPY follows the selected polarity.
- `frame` identifies the accepted scan frame. It is not a square number. A logical `h1` result does not by itself mean physical top-right; the user observed it at physical lower-left. See the orientation procedure in the test guide.

## Commands

| Request | Behavior |
|---|---|
| `PING` | Refresh the heartbeat; other commands do not refresh it |
| `STATUS` | Armed/moving/magnet state, manual origin, steps per square, polarity and latched `fault=NONE` or fault code |
| `INPUTS` | Instantaneous remapped sensor column electrical levels, in DIG_OUT order; not a full scan or necessarily the row in the last SENSOR report |
| `SCAN` | Report the latest stable whole BOARD and occupied-row SENSOR snapshot, then ACK; NOT_READY until a stable frame exists |
| `SNAPSHOT` | Wait for new stable frames after this request; return `SNAPSHOT id occupy=16HEX frame=N fault=NONE`; reject during motion or a latched fault |
| `CLEAR_FAULT` | Explicitly reset the fault latch after safely disabling outputs; invalidate carriage origin; never arm or move |
| `IDLE` | Disable outputs and disarm after completed motion, preserving the declared origin; reject while moving |
| `RAW` | Report the most recent complete, polarity-normalized pre-debounce RAW board, then ACK; also requires the initial stable frame |
| `TIMING` | Complete-frame count, last/maximum interval, intervals >=20 ms and candidate-to-accept debounce time, in microseconds |
| `PLATFORM` | LED queue-to-RMT-completion timing, >=100 ms counts/failures and free/minimum internal heap |
| `POLARITY HIGH` / `LOW` | Select occupied input level; reset debounce, move baseline and scan timing counters |
| `LED e4 0 20 0` | Set an external RGB square; accept 0..255 and cap actual channels at 32; preserve other pixels |
| `LED_CLEAR` | Clear all external RGB pixels |
| `GUIDE 0000000010100000` | Replace all pixels with green legal destinations selected by bitmask (bit 0 = a1); zero clears guidance |
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

The native UI uses correlated SNAPSHOT after DONE, rather than a cached BOARD frame, before accepting automated movement. Faults remain latched across PING, STOP and reconnect; an explicit CLEAR_FAULT is required. Reset confirms commanded safe output levels, not physical repair or measured motor position. Resolve the physical cause before resetting and resuming. Reset invalidates the manually declared carriage reference.

## Timing and Fault Handling

The Python client sends PING every 0.5 s. The MCU disables actuators after 2 s without PING while armed or active. Magnet ON is limited to 5 s and motion to 30 s. Repeated ON does not extend continuous energization. The default step schedule is approximately 100 steps/s per active axis, X then Y; delays reduce rate without catch-up bursts. LED output failure also shuts down actuators.

A 1 ms control task schedules nominal 10 ms complete-board frames with 1 ms row settling and two matching frames for debounce. The S3 control task is pinned to core1 at priority10; serial and LED workers are priorities4/3. RMT uses interrupt refilling without DMA. LED ACK means queued, not illuminated. PLATFORM does not measure optical latency. See [specification alignment](Specification_Alignment.md).

Motion-time occupancy is telemetry, not a human move; the move baseline is re-established afterward. EVENT MOVE is a candidate, not proof of legality. Multiple simultaneous changes can produce AMBIGUOUS. The Pi rules layer validates moves and compares occupancy. Recovery requires restoring the physical board when a move is rejected.

## Python Clients

`pi5/app/scb_link.py` owns the serial reader, request matching, event queue and heartbeat. Its terminal drains events while waiting for keyboard input; no Enter key is required to show sensor changes. Request timeout sends STOP and raises an error without retrying motion. `quit`/Ctrl-C closes the client and sends STOP. This does not mute firmware scanning; close the terminal to stop its display, and remove power to stop all MCU activity.

`pi5/app/board_game.py` handles rules and physical synchronization. Board mode can indicate computer moves through external LEDs and asks for manual execution; it does not automatically ARM or move motors. Promotions or ambiguous changes can use `commit <uci>` with matching occupancy. Motor path planning, automatic captures and homing are not implemented.

## Initial Sensor Test

From the project root:

```sh
esp32/.venv/bin/python pi5/app/scb_link.py --port PORT
```

Enter PING, STATUS, SCAN, RAW, INPUTS and TIMING. Keep actuator power disconnected. Use [the S3 test guide](ESP32_S3_Test_Guide.md) before LED or motion testing; no universal steps-per-square calibration is supplied.

## Raw versus confirmed sensor diagnostics

`SCAN` reports the latest confirmed occupancy and its captured row inputs. Its frame number now refreshes when an unchanged board is reconfirmed; this does not emit duplicate move events. If inputs keep changing before the required matching frames, the last confirmed board remains available and its frame number remains older.

`RAW TRACE` reports the latest COMPLETE, pre-debounce scan as the existing RAW mask plus eight `SENSOR_RAW` rows. The interactive Python terminal sends this verbose form when the user types RAW. Plain RAW remains a compact mask for automated sampling. These rows use a separate completed-frame input buffer, not live partially overwritten scan storage. RAW is available after the first complete scan, even before the board first stabilizes. The terminal prefixes these rows with `RAW (before debounce)`; game logic must not treat them as accepted moves. Comparing RAW with SCAN distinguishes a stable signal from a stale confirmed snapshot; it does not calibrate sensor thresholds or prove physical wiring.
