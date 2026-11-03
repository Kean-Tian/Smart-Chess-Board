# WeMos LOLIN32 ESP32 Firmware

Standalone ESP-IDF firmware for **WeMos LOLIN32 V1.0.0 / ESP-WROOM-32**, classic dual-core Xtensa ESP32 with 4 MB Flash and no PSRAM. The current project builds for this board only. Follow the [current jumper connection table](../docs/PCB_Connection_Map.md); this map is not the original Master PCB's MCU pinout.

## Files

| Path | Purpose |
|---|---|
| main/board_pins.h | LOLIN32 GPIO map, orientation, and timing targets |
| main/scb_core.c | Scanning, debounce, physical-move tracking, USB commands, motion and watchdogs |
| main/app_main.c | Dual-core tasks, GPIO, RMT LED output and UART0 through the USB bridge |
| components/board_logic/ | Portable sensor and LED logic |
| tests/ | Host tests with simulated GPIO |
| scripts/ram_budget.py | Post-link static internal RAM check |
| scripts/package_release.py | Export checked firmware images and a flash manifest |
| scripts/flash_firmware.py | Validate release checksums and flash only a classic ESP32 |
| release/ | Most recently compiled ESP32 images and manifest; not hardware validation |

## Build

Use **Espressif ESP-IDF 5.5.3** and its matching Xtensa toolchain, with the IDF environment activated. Select the classic `esp32` target; the firmware is not interchangeable with C5, C3/C6, or S3 images.

From this directory:

```sh
idf.py set-target esp32
idf.py build
python scripts/package_release.py --build-dir build
```

The 4 MB DIO/40 MHz Flash configuration, custom partition table, 240 MHz CPU and 1 kHz FreeRTOS tick come from sdkconfig.defaults. CMake runs the conservative 264 KiB static internal RAM check after linking. The source is validated with IDF 5.5.3; other SDK versions need separate validation.

## Flash the Compiled Release

The current Mac already has a local flashing environment at `esp32/.venv`. On a new machine, create it from the project root:

```sh
python3 -m venv esp32/.venv
esp32/.venv/bin/python -m pip install esptool==4.12.0
```

From the project root:

```sh
esp32/.venv/bin/python esp32/scripts/flash_firmware.py --port /dev/cu.usbserial-XXXX --dry-run
esp32/.venv/bin/python esp32/scripts/flash_firmware.py --port /dev/cu.usbserial-XXXX
```

Replace the example with the actual serial port (`/dev/ttyUSB0` is common on the Pi). The helper validates every image checksum and the LOLIN32 manifest before invoking esptool. It checks the ESP32 image chip ID and uses bootloader address 0x1000; no whole-chip erase, eFuse changes, or --force. The previous C5 images and 0x2000 bootloader address must not be used. Keep external actuators disabled during flashing. If auto-download fails, follow the GPIO0/EN procedure in the wiring document; do not apply the old FireBeetle BOOT procedure.

For an active IDF environment, rebuilding and flashing can also be done with `idf.py -p <port> flash`. Use the generated flash addresses, not addresses copied from another chip's release.

## First Test (No Actuators)

Use a Micro-USB data cable to the onboard USB-UART bridge. Close any serial monitor before the Pi application opens the same port. UART0 is configured for 115200 baud, 8 data bits, no parity and one stop bit. The host must match these settings. Host code deasserts DTR/RTS before opening and waits 0.5 s for a possible reset transient.

Send newline-terminated commands:

```text
@1 PING
@2 STATUS
@3 TIMING
@4 PLATFORM
@5 LED a1 20 0 0
@6 LED_CLEAR
```

Expect `ACK 1 PING`, a STATUS reply, and timing/heap information. HELLO identifies `SCB_LOLIN32 1`; it is sent once at boot and may occur before a host opens the port. PING/STATUS are the repeatable connection checks. LED commands address the external RGB chain on GPIO4; the onboard active-low GPIO5 LED is not controlled by these commands. Scanning without connected sensor inputs does not prove correct occupancy.

After checking sensor wiring, polarity, and orientation, run the Pi board entry with the actual USB port:

```sh
sh pi5/start.sh board --port /dev/ttyUSB0
```

That command is run from the project root. The Pi uses the same line protocol and retains chess rules and Stockfish. No wireless connection is required.

## Timing and Output Changes

- Dual-core 240 MHz ESP32: control runs on core 1; serial output and LED workers run on core 0.
- Nominal 100 Hz complete-board scanning, 1 ms row settling, and two-frame debounce are retained. TIMING reports observed intervals and overruns.
- Classic ESP32 RMT has no DMA backend. The LED driver uses a 128-symbol hardware buffer with interrupt refilling, IRAM-safe ISR/encoder configuration, 10 MHz ticks, GRB bytes, and a 300 us reset interval. Verify the waveform against the actual LED variant.
- A one-entry overwrite queue keeps the latest pending LED state. ACK means accepted, not physically illuminated. PLATFORM reports LED completion timing, failures, and remaining internal heap.
- LED channel ceiling remains 32/255. Stockfish runs on the Pi; MCU RAM is not a chess search/transposition-table allocation.

## Motion and Board Constraints

The [connection map](../docs/PCB_Connection_Map.md) lists input-only pins, external comparator pull-ups, the required GPIO13 motor-enable pull-up, Flash/boot pins to avoid, and reserved UART0 pins. GPIO16/17 require the specified WROOM/no-PSRAM board. GPIO5's onboard LED is intentionally unused. The old C5 GPIO assignments and onboard-magnet LED demonstration are not applicable.

Motion remains bench-level X-then-Y pulses with shared active-low enable. HOME is unsupported because no limit-switch wiring is provided. ORIGIN records manual alignment. DONE proves only pulse completion. Automatic homing, obstacle avoidance, and automatic capture handling are not implemented. Heartbeat, magnet-on and motion timeouts remain active. LED output failure disables movement and releases the magnet.

## Host Tests

```sh
sh tests/run_core_tests.sh
```

Root CMake/CTest and the Mac test launcher also run the portable logic. These do not exercise real USB-UART, RMT, electrical levels, sensor noise, or physical movement. Target compilation and all hardware measurements are reported separately.
