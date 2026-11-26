# ESP32-S3 PCB V3 Bench Firmware

These separate S3 applications replace the main firmware when flashed. All use the shared board_pins.h and SCB PCB V3 target; no S2 configuration is retained. Native USB is the default where a protocol is provided. The board needs external power because J5 VBUS connects to ESD protection and a capacitor, not the system power rail.

| Folder | Function | Communication |
|---|---|---|
| gpio46_high | GPIO46 HIGH after app startup; D6 test only | No protocol, scans or actuator tasks |
| gpio_low | Hold sensor A0/A1/A2 at 000 (default GPIO10/9/8) | No protocol; PING is expected to time out |
| gpio_a0_high | Hold sensor A0=1, A1=A2=0 (address001) | PING, STATUS, INPUTS, STOP/DISARM; scanning deliberately disabled |
| corexy_s3 | Explicitly calibrated CoreXY carriage bench | Native USB or selected J6 UART; no automatic calibration, magnet held OFF |

The MUX and CoreXY benches disable drivers and magnet on application startup. The GPIO46-only bench configures only GPIO46 and does not initialize other application outputs. ROM/reset pin states are not controlled by the application. Use a new build directory and target esp32s3, use the shared V3 pin map, and flash only with actuator power disconnected. Restore the main S3 release for full-board scanning. See [firmware README](../README.md) and [CoreXY guide](corexy_s3/README.md).
