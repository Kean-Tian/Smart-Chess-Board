# ESP32-S3 Firmware

This directory is a standalone ESP-IDF / PlatformIO project targeting a bare ESP32-S3 chip with external 16 MB Flash and no PSRAM.

## Main Files and Directories

| File or directory | Purpose |
|---|---|
| `main/board_pins.h` | Single source of GPIO configuration and orientation parameters for the PCB |
| `main/scb_core.c` | Row-by-row scanning, commands, motion, electromagnet control, and timeout state |
| `main/app_main.c` | ESP-IDF GPIO, RMT, and USB Serial/JTAG drivers |
| `components/board_logic/` | Portable MCU logic for debouncing, candidate move events, and LED mapping |
| `tests/` | Host tests with simulated GPIO |
| `release/` | Most recently compiled binaries, flash addresses, and checksums |

GPIO assignments: LED=2, MUX=4/5/6, DIG_OUT1–8=7–14, electromagnet=33, X STEP/DIR=34/35, Y STEP/DIR=36/37, shared EN=38, USB D−/D+=19/20.
See the [PCB connection map](../docs/PCB_Connection_Map.md) for ribbon-cable and package-pin details.

## Build and Flash

```sh
pio run
pio run -t upload --upload-port /dev/ttyACM0
```

PlatformIO is pinned to `espressif32@6.9.0` (ESP-IDF 5.3.1). `esp32-s3-devkitc-1` supplies the chip build definitions; project-specific pin and Flash settings override them to match the actual bare-chip PCB.

Alternatively, use ESP-IDF 5.3.1:

```sh
idf.py set-target esp32s3
idf.py build
idf.py -p /dev/ttyACM0 flash
```

GPIO33–37 are used for motion and electromagnet control. Do not enable octal Flash/PSRAM configurations that occupy these pins.

## Tests Without Hardware

```sh
sh tests/run_core_tests.sh
```

The unified CMake / CTest tests can also be run from the project root. These tests do not constitute hardware validation.

## Hardware Setup and Limitations

Verify the four corner coordinates, occupancy polarity, and LED orientation before calibrating motor directions and steps per square.
The PCB has no homing limit-switch inputs, so `HOME` is explicitly unsupported. `ORIGIN` only records a manually aligned position.
`DONE` indicates that step-pulse output has finished; it does not replace physical board-state confirmation. See the [protocol](../docs/USB_Protocol.md) for USB commands and default protection timing.

The old Pi GPIO, Linux SPI LED, and shared-STEP drivers have been removed. The current hardware path uses ESP-IDF: RMT for LEDs, independent STEP signals for the two axes, and a shared active-low EN signal.
