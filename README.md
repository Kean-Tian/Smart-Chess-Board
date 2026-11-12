# SCB stepper demo (ESP32-S2-Saola-1, ESP-IDF, VS Code)

Drives two NEMA-17 motors through two A4988 drivers. Pin numbers live in `main/board_pins.h`.

## 1. Install the tools (once)
1. Install Visual Studio Code.
2. Install the extensions: **ESP-IDF** (publisher: Espressif Systems, id `espressif.esp-idf-extension`) and **C/C++** (`ms-vscode.cpptools`).
3. Press `F1`, run **ESP-IDF: Configure ESP-IDF Extension**, and follow the installer (in v2.x of the extension it uses the Espressif Installation Manager). Choose the latest stable ESP-IDF release.
4. Windows only: if the board does not show up as a COM port, install the CP210x USB-to-UART driver.

## 2. Open and build
1. `File > Open Folder...` and pick this folder (the one containing the top-level `CMakeLists.txt`).
2. `F1` -> **ESP-IDF: Set Espressif Device Target** -> `esp32s2` (later: `esp32s3` for the custom board).
3. `F1` -> **ESP-IDF: Select Port to Use** -> the Saola-1's serial port (use the micro-USB port labelled for the UART bridge).
4. `F1` -> **ESP-IDF: Build, Flash and Monitor** (or use the status-bar icons).
5. If flashing fails to connect: hold **BOOT**, tap **RESET**, release BOOT, then flash again.

## 3. Wiring (each A4988)
| A4988 pin | Connect to |
|---|---|
| VMOT / GND (next to it) | motor supply (8-35 V) with a 47-100 uF capacitor right at the pins |
| VDD / GND | ESP32 3V3 and GND |
| STEP, DIR | GPIO from `board_pins.h` (never leave floating) |
| /ENABLE | `PIN_MOTOR_EN`, plus a 10 k pull-up to 3V3 so the motors stay off while the ESP32 boots |
| RESET + SLEEP | tie together |
| MS1-MS3 | leave open for full-step (internal pull-downs); pull high for microstepping |
| 1A/1B, 2A/2B | the two motor coils |

All grounds must be common (ESP32, both A4988s, motor supply). Power down before connecting or disconnecting a motor.

## 4. Set the current limit before connecting the motors
`VREF = 8 x I_max x R_sense` with R_sense = 0.068 ohm on current Pololu boards (older boards: 0.05 ohm). In full-step mode both coils conduct and the current is limited to about 70 % of the set limit.
Measure VREF on the potentiometer while the board is powered, with the motor disconnected.

## 5. Tuning
Edit `START_SPS`, `MAX_SPS`, `ACCEL_SPS2` (and `MICROSTEP`) at the top of `main/main.c`. If the motor stalls or buzzes instead of turning, lower MAX_SPS or ACCEL_SPS2, or raise the current limit within the motor's rating.
