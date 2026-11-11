# ESP32-S2-Saola-1 Test Guide

This guide applies to the **main S2 full-scan firmware**, current GPIO36/37/38 MUX wiring and GPIO1..8 sensor inputs. It separates computer-only tests from connected-board measurements. The fixed-MUX programs under `esp32/bench/` are optional alternatives and must not be confused with the main release.

## Test Status

| Area | Current evidence | Remaining work |
|---|---|---|
| S2 target build and release validation | Compiled ESP-IDF firmware; checked S2 headers, hashes and flash addresses | Reflash after firmware changes |
| Portable logic and Python interfaces | Automated simulated-GPIO/serial tests; see latest validation record | Does not establish electrical operation |
| Computer-to-S2 USB-UART | Earlier successful PING, STATUS, SCAN, RAW and TIMING session | Repeat after flashing; Pi 5 execution not verified |
| Physical sensor response | User observed magnet-dependent BOARD/EVENT changes and readable SENSOR output | Verify all 64 positions and repeatability |
| Sensor polarity | Firmware defaults to HIGH; latest debugging found only 3.3 V/GND connected and no magnet response | Supply the missing comparator 5 V rail, then recheck polarity and every row |
| Physical coordinates | Logical mapping and V2 schematic networks traced | Not calibrated: physical lower-left displayed logical h1 |
| Scan timing | Earlier session reported last interval 10000 us, maximum 12000 us, zero misses | Sustained tests with current firmware, connected PCB and other loads |
| External LEDs | Driver code and simulated mappings exist | Actual waveform, order and optical latency |
| Motors and electromagnet | Portable pulse/control/watchdog tests | Wiring, calibration, travel, load and transport tests |

No board is flashed and no serial port is opened by the computer-only checks below. The latest packaged image is not automatically marked hardware-tested just because an earlier S2 image ran successfully.

## 1. Computer-Only Regression Tests

From the project root on the current Apple Silicon Mac:

```sh
sh SCB_Computer_Test.command --check-only
```

This runs ten suites plus real local Stockfish/libchess checks. MCU inputs and serial devices are simulated; cloud responses are simulated. It needs the bundled Mac binaries and actual Stockfish file, not a Git LFS pointer. Install Git LFS and run `git lfs pull` if needed. Normal game startup keeps checks silent and stores their output in `tools/mac_test/latest_check.log`.

To rebuild and test from source:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=/usr/bin/python3
cmake --build build -j 4
ctest --test-dir build --output-on-failure
sh esp32/tests/run_core_tests.sh
```

Use a Python interpreter matching the native library architecture; an x86_64 Python cannot load an arm64 rules library. The sanitizer entry rebuilds the portable MCU tests without hardware.

Coverage includes all 64 logical occupancy bits, empty/full boards, polarity, debounce, move candidates, invalid/partial command frames, output guards, simulated motion/watchdogs, synchronized SENSOR traces, rate limiting, readable occupancy, live terminal events, request matching/timeouts and release-image validation. It does not simulate the analog Hall/comparator circuit or prove physical orientation.

## 2. Build and Flash

See [the firmware README](../esp32/README.md) for ESP-IDF 5.5.3 setup, `esp32s2` target selection and packaging. From the project root:

```sh
esp32/.venv/bin/python -m serial.tools.list_ports -v
esp32/.venv/bin/python esp32/scripts/flash_firmware.py --port PORT --baud 57600 --no-compress --dry-run
esp32/.venv/bin/python esp32/scripts/flash_firmware.py --port PORT --baud 57600 --no-compress
```

Replace PORT with the current enumerated device; `/dev/cu.usbserial-2140` was observed previously, not guaranteed after reconnecting. Close all serial clients first. Keep actuator power disconnected. A dry run only validates and prints the command. Successful flashing must finish image verification without errors; press RESET if necessary to start the application.

## 3. USB-Only Communication

Keep external actuator power off. Open the main terminal:

```sh
esp32/.venv/bin/python pi5/app/scb_link.py --port PORT
```

Enter:

```text
PING
STATUS
INPUTS
TIMING
PLATFORM
```

Expect an ACK for PING, a STATUS reply containing `armed=0 moving=0 magnet=0`, eight input characters, advancing full-frame counts and platform statistics. GPIO1..8 have no internal pull resistors enabled: with the sensor PCB disconnected they can float. Random BOARD values or AMBIGUOUS events in this condition are not valid sensor measurements. The SCB terminal maintains PING automatically; `quit` releases the port and sends STOP.

If PING times out, check the actual port, close competing monitors, confirm the main release is flashed, and reset the board. `HELLO SCB_S2_SAOLA_1 1` identifies the main firmware; a fixed-MUX bench identifier means full scanning is not running.

## 4. Connect and Check the Sensor PCB

Disconnect power while wiring, then follow the [V2 contact table](PCB_Connection_Map.md). Use a common ground and both required supply rails: J1 contact14 = +3V3 for row-selection logic; contact16 = +5V for LM339 U3/U4 (and the LED/buffer rail); contacts10/12 = GND. The latest no-response fault had only 3.3 V/GND connected. Correct that missing supply before deciding polarity. Do not apply 5 V to GPIO/DIG_OUT signal inputs. Connect by DIG_OUT name: DIG_OUT1→GPIO1 through DIG_OUT8→GPIO8. J1 contacts 1..8 are not in that numerical signal order.

Use MUX_IN1/A0→GPIO36, MUX_IN2/A1→GPIO37, MUX_IN3/A2→GPIO38. All sensor inputs remain inputs; do not configure them as outputs to force a LOW. Power the board and start the terminal. With magnets removed, check the stable board. Place a magnet on one sensor, hold it still until debounce completes, remove it, and repeat.

```text
STATUS
SCAN
RAW
INPUTS
```

The normal polarity is HIGH = occupied. If placement consistently looks like removal, compare raw captured levels with physical actions before using `POLARITY HIGH` or `POLARITY LOW`. A polarity command resets scan statistics, debounce and event baseline. INPUTS is instantaneous and may sample a different row than the previous printed trace; use SENSOR messages for synchronized row/input comparisons.

SCAN reports the latest complete stable frame and forces occupied-row debug output. RAW is the latest completed polarity-normalized frame before debounce. Neither command is a request to read just one row. The background scanner runs continuously.

## 5. Calibrate Physical Orientation and All 64 Positions

Do not assume a printed rank is counted from the top or a file from the left. Current zero orientation flags give MUX address index 0→logical rank1 and DIG_OUT1→logical file a. Printed INPUTS characters run DIG_OUT1 to DIG_OUT8.

For example:

```text
MUX(A2,A1,A0)=000 [GPIO36,37,38=000] | INPUTS(DIG_OUT1..8)=00000001 | OCCUPY=h1
```

This says address0 / DIG_OUT8 / logical h1. The user physically triggered the lower-left corner, so the earlier top-right description was incorrect. One corner does not determine the complete rotation/reflection. No orientation changes have been inferred automatically.

Choose a viewing direction and photograph or label it. Test each of the four corners with exactly one magnet, recording MUX, INPUTS, OCCUPY and, if accessible, HE number. Decide which physical corner should be a1. Then adjust `SCB_SENSOR_REVERSE_ROWS` and/or `SCB_SENSOR_REVERSE_COLUMNS` only if the measured mapping requires them; rebuild, package and reflash. A transposed row/column arrangement requires an explicit mapping change, not just a flip flag.

After the corners agree, move one magnet through all 64 physical positions. Record one stable occupied square per position and confirm it clears on removal. Then test multiple magnets, lift/return, and moving one magnet between positions. A single placement can be reported as RETURN depending on the move-tracker baseline; prioritize correct occupied squares first. Hall occupancy cannot identify piece type or color. Calibrate external LED orientation separately.

## 6. Scan Timing Without External LEDs

Run outside the terminal; only one process can own the port:

```sh
esp32/.venv/bin/python pi5/app/board_diagnostics.py --port PORT --seconds 10 --output pi5/runtime/S2_Scan_Timing.json
```

The default mode checks scanning and does not request external LED changes. `led_software_pass` is null (not tested), not a fabricated LED pass. Acceptance requires observed complete-frame rate >50 Hz, maximum observed interval <20000 us and zero scan misses. Target configuration is 100 Hz, but the JSON reports observations. Debounce timing starts at the first completed candidate frame, not the physical moment the magnet moved.

The automatic debug-output limit is five board snapshots per second, not five scans per second. Each snapshot may contain several occupied-row lines. Repeat longer/load tests after the initial check. Historical short-session numbers do not prove all workloads meet the specification.

## 7. Optional External LED Test

Only after checking the external RGB supply, common ground and required level shifter, use GPIO17 data. GPIO18 is the onboard RGB LED and is not controlled by these commands.

```text
LED a1 20 0 0
LED_CLEAR
MARK e2 e4 LEGAL
LED_CLEAR
```

Check actual pixel position and color; MARK should show source blue and destination green. ACK is not proof of light output. For queue-to-RMT-completion measurements:

```sh
esp32/.venv/bin/python pi5/app/board_diagnostics.py --port PORT --seconds 10 --exercise-leds --output pi5/runtime/S2_LED_Timing.json
```

This also requires recorded LED completion <100 ms with zero late/failed counts. It still does not measure physical-event-to-visible-light latency. Motors are never armed by this diagnostic.

## 8. Motor and Electromagnet Bench Tests

These remain separate, unverified hardware tests. Before powering drivers, verify the external motor-enable pull-up, intended supplies, mechanics and clear travel. Keep the heartbeat client active. Begin with STATUS/STOP, then calibrate direction and distance using small JOG commands. SET_STEPS requires a measured value; ORIGIN records manual alignment. Do not copy a guessed step count into production operation.

GOTO/MOVE require ARM and applicable calibration/origin; MOVE uses X-then-Y motion without collision avoidance. DONE confirms pulse completion only. Check actual motion, magnet release and resulting sensor board state. HOME is unsupported. STOP disables actuators but keeps scanning active. Serial display can be stopped by quitting the client; cutting MCU power stops its scanning. Validate watchdog shutdown separately under controlled bench conditions.

## Record Results

Keep reports in `pi5/runtime/` (ignored by Git). For each physical test record the firmware SHA256, board, wiring, viewing direction, supply conditions, action, expected result and actual result. Update validation status only when that specific measurement has been performed. Historical observations and the latest host tests are recorded separately in [validation/latest.json](validation/latest.json).
