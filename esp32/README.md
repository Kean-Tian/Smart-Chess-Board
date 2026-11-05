# ESP32-S2-Saola-1 Firmware

The current firmware targets **ESP32-S2-Saola-1**, a single-core Xtensa ESP32-S2 board with 4 MB Flash. WROOM/WROVER variants are supported with PSRAM disabled. Use the current jumper wiring in [PCB connections](../docs/PCB_Connection_Map.md); the older Master PCB MCU footprint is a separate hardware design.

## Files

| Path | Purpose |
|---|---|
| `main/board_pins.h` | Current S2 GPIO map, sensor polarity, orientation flags and timing settings |
| `main/scb_core.c` | Complete-board scanning, debouncing, sensor traces, commands, motion and watchdogs |
| `main/app_main.c` | GPIO/UART initialization, single-core tasks and external RMT LED output |
| `tests/` | Portable control-logic tests with simulated GPIO |
| `bench/` | Optional fixed-MUX test firmware; does not run full-board scanning |
| `scripts/package_release.py` | Export a fresh target build and checked image manifest |
| `scripts/flash_firmware.py` | Validate release hashes, addresses and S2 image headers before flashing |
| `release/` | Main full-scan firmware images; consult the manifest for their build date |

## Build the Main Firmware

Activate **ESP-IDF 5.5.3** and its matching Xtensa toolchain, then run from `esp32/`:

```sh
idf.py set-target esp32s2
idf.py build
python scripts/package_release.py --build-dir build
```

Use a clean build when changing chip targets. Images for classic ESP32, C5 or S3 are not interchangeable with this firmware. Defaults are 4 MB DIO/40 MHz Flash, 240 MHz CPU, a 1 kHz FreeRTOS tick and no PSRAM. A post-link check limits static internal RAM to 264 KiB; dynamic heap allocations must be checked separately.

## Flash the Main Release

Run from the project root. On a new computer, prepare the environment:

```sh
python3 -m venv esp32/.venv
esp32/.venv/bin/python -m pip install esptool==4.12.0 pyserial==3.5
esp32/.venv/bin/python -m serial.tools.list_ports -v
```

Close the SCB terminal or any other serial monitor. Replace `PORT` with the detected port, for example `/dev/cu.usbserial-2140` on the current Mac or `/dev/ttyUSB0` on Linux:

```sh
esp32/.venv/bin/python esp32/scripts/flash_firmware.py --port PORT --baud 57600 --no-compress --dry-run
esp32/.venv/bin/python esp32/scripts/flash_firmware.py --port PORT --baud 57600 --no-compress
```

The lower baud and uncompressed writes succeeded during earlier S2 upload troubleshooting. The helper also supports its normal 115200-baud compressed mode without these options. Baud changes here affect flashing only; application communication remains 115200.

The helper validates every image hash, S2 image chip ID 2, and addresses `0x1000` (bootloader), `0x8000` (partitions), `0x10000` (application). It does not erase the entire chip or force a chip mismatch. If automatic download fails, hold BOOT, press and release RESET, then release BOOT when esptool connects. Press RESET after flashing if the application does not start.

## Test the Connected Board

Follow [the S2 test guide](../docs/ESP32_S2_Test_Guide.md) for staged USB, sensor, timing and optional actuator tests. Start with actuator power disconnected.

```sh
esp32/.venv/bin/python pi5/app/scb_link.py --port PORT
```

The main firmware identifies itself as `HELLO SCB_S2_SAOLA_1 1`. HELLO is sent once at startup and may precede the host connection; use PING/STATUS as repeatable checks. The terminal performs an initial SCAN and displays sensor changes without waiting for keyboard input.

```text
PING
STATUS
INPUTS
SCAN
RAW
TIMING
PLATFORM
```

`INPUTS` reads the eight electrical levels for whichever row is selected at that instant. `SCAN` reports the latest stable **complete 64-square board**; it does not start a one-row scan. Raw input levels and row addresses in `SENSOR` messages were captured with the accepted board frame. Occupancy is displayed as square names, while the wire mask remains 16 hexadecimal digits.

Sensor defaults are **HIGH = occupied**, MUX A0/A1/A2 = GPIO36/37/38 and DIG_OUT1..8 = GPIO1..8. Row and column orientation flags are currently zero. Physical orientation is **not calibrated**: the user reported that the physical lower-left sensor displayed `h1`. Do not label a raw row as top/bottom until all four corners and all 64 positions have been verified. No orientation flip has been applied based on that one observation.

## Scheduling and Outputs

The single-core control task runs at priority 10, serial output at 4 and LED output at 3. No task is pinned to a nonexistent second core. Scanning targets a 10 ms complete-frame period, with 1 ms row settling and two matching complete frames for debounce. TIMING reports observed frame periods and overruns.

The external RGB data pin is **GPIO17**. The board's GPIO18 RGB LED is unused. RMT uses a 128-symbol hardware buffer, interrupt refilling without DMA, 10 MHz ticks, GRB bytes and a 300 us reset interval. A one-entry queue keeps the latest pending LED state. ACK confirms acceptance, not physical illumination. PLATFORM reports queue-to-RMT-completion timing and internal free/minimum heap. LED channel values are capped at 32/255. Actual LED waveform and optical response remain unverified.

Motion remains bench-level X-then-Y pulse control. HOME returns `NO_HOME_SWITCHES`; ORIGIN records manual alignment. DONE confirms pulse completion, not successful piece transport. Automatic homing, collision avoidance and capture handling are not implemented. Boot, STOP, watchdog and LED-failure handling disable motion and release the electromagnet. STOP does not stop board scanning or mute serial reports.

## Host Tests

From `esp32/`:

```sh
sh tests/run_core_tests.sh
```

The root CMake/CTest entry and `sh SCB_Computer_Test.command --check-only` also run the S2-mapped portable core. These use simulated inputs and do not open a serial port. Test coverage and the distinction between software results and hardware observations are documented in the S2 test guide and [validation record](../docs/validation/latest.json).
