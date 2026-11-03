# FireBeetle 2 ESP32-C5 Firmware

Standalone ESP-IDF firmware for **DFRobot DFR1222 V1.0 / ESP32-C5-WROOM-1-N4**, with 4 MB Flash and no PSRAM. This project now builds for C5 only. It is a jumper-wire bench controller; use the [current wiring table](../docs/PCB_Connection_Map.md) before connecting the sensor board, LED level shifter, motor drivers, or electromagnet driver.

## Files

| Path | Purpose |
|---|---|
| main/board_pins.h | C5 GPIO map, orientation, and timing targets |
| main/scb_core.c | Scanning, debounce, physical-move tracking, USB commands, motion and watchdogs |
| main/app_main.c | Single-core tasks, GPIO, RMT LED output and native USB Serial/JTAG |
| components/board_logic/ | Portable sensor and LED logic |
| tests/ | Host tests with simulated GPIO |
| scripts/ram_budget.py | Post-link static internal RAM check |
| scripts/package_release.py | Export checked firmware images and a flash manifest |
| scripts/flash_firmware.py | Validate release checksums and flash only an ESP32-C5 |
| release/ | Most recently compiled C5 images and manifest; not hardware validation |

## Build

Use **Espressif ESP-IDF 5.5.3** and its RISC-V toolchain, with the IDF environment activated. The old PlatformIO configuration was removed because its target/toolchain routing did not support C5. Do not select a C3/C6 or an Xtensa target as a substitute.

From this directory:

```sh
idf.py set-target esp32c5
idf.py build
python scripts/package_release.py --build-dir build
```

The 4 MB DIO/80 MHz Flash configuration, custom partition table, 240 MHz CPU and 1 kHz FreeRTOS tick come from sdkconfig.defaults. CMake runs the conservative 264 KiB static internal RAM check after linking. The source is validated with IDF 5.5.3; other SDK versions need separate validation.

## Flash the Compiled Release

The current Mac already has a local flashing environment at `esp32/.venv`. On a new machine, create it from the project root:

```sh
python3 -m venv esp32/.venv
esp32/.venv/bin/python -m pip install esptool==4.12.0
```

From the project root:

```sh
esp32/.venv/bin/python esp32/scripts/flash_firmware.py --port /dev/cu.usbmodemXXXX --dry-run
esp32/.venv/bin/python esp32/scripts/flash_firmware.py --port /dev/cu.usbmodemXXXX
```

Replace the example with the actual serial port (`/dev/ttyACM0` is common on the Pi). The helper validates every image checksum and the C5 manifest before invoking esptool. It does not erase the whole chip, write eFuses, or flash a different chip with --force. Keep external actuators disabled during flashing. If necessary hold BOOT, tap RST, release BOOT, then flash; release BOOT and reset afterward.

For an active IDF environment, rebuilding and flashing can also be done with `idf.py -p <port> flash`. Use the generated flash addresses, not addresses copied from another chip's release.

## First Test (No Actuators)

Use a USB data cable to the onboard Type-C port. Close any serial monitor before the Pi application opens the same port. 115200 is the host client's setting; the transport is native USB Serial/JTAG rather than an external UART bridge.

Send newline-terminated commands:

```text
@1 PING
@2 STATUS
@3 TIMING
@4 PLATFORM
@5 LED a1 20 0 0
@6 LED_CLEAR
```

Expect `ACK 1 PING`, a STATUS reply, and timing/heap information. HELLO identifies `SCB_ESP32C5 1`; it is sent once at boot and may occur before a host opens the port. PING/STATUS are the repeatable connection checks. LED commands address the external RGB chain on GPIO2, not the onboard D13 indicator. Scanning without connected sensor inputs does not prove correct occupancy.

After checking sensor wiring, polarity, and orientation, run the Pi board entry with the actual USB port:

```sh
sh pi5/start.sh board --port /dev/ttyACM0
```

That command is run from the project root. The Pi uses the same line protocol and retains chess rules and Stockfish. No wireless connection is required.

## Timing and Output Changes

- One 240 MHz application CPU; control and LED workers are separate tasks on the same CPU. There is no task pinned to core 1.
- Nominal 100 Hz complete-board scanning, 1 ms row settling, and two-frame debounce are retained. TIMING reports observed intervals and overruns.
- C5 RMT has no DMA backend. The LED driver uses a 96-symbol hardware buffer with interrupt refilling, IRAM-safe ISR/encoder configuration, 10 MHz ticks, GRB bytes, and a 300 us reset interval. Verify the waveform against the actual LED variant.
- A one-entry overwrite queue keeps the latest pending LED state. ACK means accepted, not physically illuminated. PLATFORM reports LED completion timing, failures, and remaining internal heap.
- LED channel ceiling remains 32/255. Stockfish runs on the Pi; MCU RAM is not a chess search/transposition-table allocation.

## Motion and Board Constraints

The [connection map](../docs/PCB_Connection_Map.md) explains GPIO27's required external enable pull-up and GPIO28's BOOT/open-drain direction output. Do not press BOOT during motion. N4/no-PSRAM is required for GPIO15. GPIO0 power control and GPIO1 battery ADC are untouched. GDI must remain disconnected.

Motion remains bench-level X-then-Y pulses with shared active-low enable. HOME is unsupported because no limit-switch wiring is provided. ORIGIN records manual alignment. DONE proves only pulse completion. Automatic homing, obstacle avoidance, and automatic capture handling are not implemented. Heartbeat, magnet-on and motion timeouts remain active. LED output failure disables movement and releases the magnet.

## Host Tests

```sh
sh tests/run_core_tests.sh
```

Root CMake/CTest and the Mac test launcher also run the portable logic. These do not exercise real C5 USB, RMT, electrical levels, sensor noise, or physical movement. Target compilation and all hardware measurements are reported separately.
