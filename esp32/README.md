# SCB Master PCB V2 Firmware — ESP32-S3

This replaces the S2 development-board target with the bare ESP32-S3 and external W25Q128JVS (16 MB) shown in the supplied V2 schematic. It retains scanning, two-frame debounce, move events, LED feedback, watchdogs and guarded motion commands. No PSRAM or MCU chess engine is enabled. See [exact cable/GPIO map](../docs/PCB_Connection_Map.md).

**Motor STEP/DIR differ between the supplied schematic and PCB pad nets.** The user confirmed the board was fabricated from the supplied PCB. Default is `CONFIG_SCB_MOTOR_PCB_ROUTING=y`: X STEP=35/DIR=34 and Y STEP=37/DIR=36. Actuators stay disabled until explicit commands and calibration. A firmware build does not establish physical motion accuracy or collision-free travel.

## Build

Use ESP-IDF 5.5.3 or newer, validated here with 5.5.3. Use a NEW build directory; do not reuse an S2 sdkconfig/build cache:

```sh
cd esp32
idf.py -B build-s3 -D SDKCONFIG=sdkconfig.s3 set-target esp32s3
idf.py -B build-s3 -D SDKCONFIG=sdkconfig.s3 menuconfig
idf.py -B build-s3 -D SDKCONFIG=sdkconfig.s3 build
python scripts/package_release.py --build-dir build-s3
```

Settings: 16 MB DIO/40 MHz Flash, 240 MHz dual-core S3, no PSRAM, 1 kHz FreeRTOS tick. The single-owner control task is pinned to core 1; serial and RMT workers do not mutate the controller state. Static internal RAM is limited to 264 KiB as a project control ceiling, not as the S3's total memory capacity.

Menuconfig: **SCB local communication** selects J5 native USB Serial/JTAG (default) or J6 wired UART1. **SCB PCB V2 wiring** selects the verified motor copper variant and optional custom name-crossed cable. Default cable is straight IDC16 pin n to pin n; firmware compensates its crossed signal labels.

## Flash

From the repository root:

```sh
python3 -m venv esp32/.venv
esp32/.venv/bin/python -m pip install esptool==4.12.0 pyserial==3.5
esp32/.venv/bin/python -m serial.tools.list_ports -v
esp32/.venv/bin/python esp32/scripts/flash_firmware.py --port ACTUAL_PORT --dry-run
esp32/.venv/bin/python esp32/scripts/flash_firmware.py --port ACTUAL_PORT
```

Use the enumerated S3 native USB port, typically `/dev/cu.usbmodem...` on macOS or `/dev/ttyACM0` on Pi. Bootloader is at **0x0** (S3), partition table at 0x8000, application at 0x10000. Never use the old S2 bootloader offset 0x1000 or force a chip mismatch. The helper validates chip ID, flash size, addresses and checksums before opening the port.

J5 VBUS is unconnected: provide the intended external board supply, with actuator power disconnected during initial flash/tests. Enter download mode if needed: hold BOOT, press/release RESET, then release BOOT. The J6 application UART pins 18/17 are not the unconnected ROM UART0 pins 43/44. GPIO19/20 remain reserved for native USB even in a wired-UART application build.

## Test

```sh
sh esp32/tests/run_core_tests.sh
esp32/.venv/bin/python pi5/tests/pcb_mapping_tests.py
esp32/.venv/bin/python pi5/app/scb_link.py --port ACTUAL_PORT
```

Use PING, STATUS, SCAN, RAW, INPUTS, TIMING and PLATFORM. HELLO is `SCB_MASTER_PCB_V2_S3 1`. Protocol and Pi UI behavior are retained. A port name or ACK alone is not proof of correct physical sensing or LED illumination. Start with an empty board and one magnet, verify polarity and all 64 coordinates, then test external LEDs. No automatic calibration hides false occupancy. Native USB is not Wi-Fi and does not require internet.

See [test guide](../docs/ESP32_S3_Test_Guide.md), [protocol](../docs/USB_Protocol.md) and [bench applications](bench/README.md). Calibration is volatile. HOME remains unavailable because no home switches are connected. The main firmware preserves its existing guarded X/Y motion algorithm; the separate CoreXY bench requires explicit measured coefficients/scale/limits/profile. No physical actuator motion has been validated by host tests.
