# ESP32-S3 PCB V2 Bench Firmware

These separate S3 applications replace the main firmware when flashed. All use the shared board_pins.h and SCB PCB V2 target; no S2 configuration is retained. Native USB is the default where a protocol is provided. The board needs external power because J5 VBUS is unconnected.

| Folder | Function | Communication |
|---|---|---|
| gpio_low | Hold sensor A0/A1/A2 at 000 (default GPIO6/5/4) | No protocol; PING is expected to time out |
| gpio_a0_high | Hold sensor A0=1, A1=A2=0 (address001) | PING, STATUS, INPUTS, STOP/DISARM; scanning deliberately disabled |
| corexy_s3 | Explicitly calibrated CoreXY carriage bench | Native USB or selected J6 UART; no automatic calibration, magnet held OFF |

Each test disables drivers and magnet on application startup. ROM/reset pin states are not controlled by the application. Use a new build directory and target esp32s3, configure the verified motor PCB/schematic option, and flash only with actuator power disconnected. Restore the main S3 release for full-board scanning. See [firmware README](../README.md) and [CoreXY guide](corexy_s3/README.md).
