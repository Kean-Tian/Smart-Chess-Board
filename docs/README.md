# Interface and Validation Documentation

- [S2 test guide](ESP32_S2_Test_Guide.md): staged computer-only, USB, sensor, orientation, timing and optional output tests.
- [PCB connection map](PCB_Connection_Map.md): current S2 GPIO numbers, Sensor PCB V2 J1 contacts and logical mapping.
- [USB protocol](USB_Protocol.md): commands, synchronized sensor traces, readable terminal output and motion limitations.
- [Software specification alignment](Specification_Alignment.md): configured targets and measurement boundaries.
- [Latest validation](validation/latest.json): current build/software checks, separate historical hardware observations and remaining tests.
- `validation/history/`: preserved older results and wiring targets; do not use them as the current configuration.

Routine build/start instructions are in the Pi and ESP32 README files. The current MCU is ESP32-S2-Saola-1. Original Master PCB/S3 references are hardware history, not the current test-controller configuration. Physical sensor orientation remains uncalibrated.
