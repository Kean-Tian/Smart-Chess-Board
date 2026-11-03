# FireBeetle 2 ESP32-C5 Bench Connections

Current firmware target: **DFRobot DFR1222 V1.0, ESP32-C5-WROOM-1-N4**, 4 MB Flash, no PSRAM. The following is a proposed jumper-wire test harness based on the manufacturer schematic and module datasheet. It is not the copper routing of the team's earlier bare-chip Master PCB. Firmware and pin assignments have not been verified on connected hardware.

## Signal Mapping

All numbers below are native GPIO numbers, not Arduino D numbers or module-pad numbers. The sensor PCB uses the original network names. Connect by net name, not by the numeric order of ribbon contacts.

| Function / existing PCB net | FireBeetle GPIO | Board label | Notes |
|---|---:|---|---|
| LED_IN_3V3, input to external 74AHCT1G125 | 2 | 2 / A1 | External RGB-chain data; not onboard indicator |
| MUX_IN1 / A0 | 3 | 3 / A2 | Least significant row address bit |
| MUX_IN2 / A1 | 4 | 4 / A3 | Row address |
| MUX_IN3 / A2 | 5 | 5 / A4 | Most significant row address bit |
| DIG_OUT1 / file a | 6 | 6 / D12 | 3.3 V digital input |
| DIG_OUT2 / file b | 7 | 7 / D11 | JTAG strap; do not change eFuses |
| DIG_OUT3 / file c | 8 | 8 / D2 | Digital input |
| DIG_OUT4 / file d | 9 | 9 / SDA | Digital input; no I2C driver used |
| DIG_OUT5 / file e | 10 | 10 / SCL | Digital input; no I2C driver used |
| DIG_OUT6 / file f | 23 | 23 / SCK | Digital input; no SPI driver used |
| DIG_OUT7 / file g | 24 | 24 / MOSI | Digital input |
| DIG_OUT8 / file h | 25 | 25 / MISO | SDIO edge strap, not SPI boot mode selection |
| EM_CTRL to external MOSFET driver | 15 | 15 / D13 | Also drives the onboard LED; N4/no-PSRAM module only |
| X_STEP to A4988 | 12 | RX | Pulse output, not UART RX in this firmware |
| X_DIR to A4988 | 11 | TX | ROM may print here before application startup; keep EN disabled |
| Y_STEP to A4988 | 26 | 26 / D3 | Boot strap; high-impedance driver input at reset |
| Y_DIR to A4988 | 28 | 28 / D9 / BOOT | Open-drain; board's pull-up supplies HIGH |
| MOTOR_EN, shared active-low A4988 enable | 27 | 27 / D6 | Add 10k pull-up to the same 3.3 V logic rail |
| USB D- / D+ | 13 / 14 | Onboard USB-C | Already routed on board; no external signal wiring |

The application uses all 18 exposed I/O signals plus the two onboard USB signals. GPIO0 controls 3V3_C and GPIO1 senses the battery; neither is used or reconfigured. Leave the GDI display connector unused because its nets share the pins above. The project TFT remains connected to the Pi through HDMI and USB touch.

## Reset, BOOT, and Logic Levels

- GPIO27 and GPIO28 must be HIGH at reset for normal flash boot. Do not attach a circuit that pulls them LOW during reset. Add an external 10k pull-up on MOTOR_EN/GPIO27 so the motor drivers remain disabled before software starts. Firmware cannot replace this reset-time resistor.
- GPIO28 is shared with the BOOT button. The firmware uses open-drain output plus pull-up, so the button does not short a push-pull HIGH output. Never press BOOT during motion: it can force the Y direction LOW. When a requested HIGH reads LOW, the output adapter reports failure before sending the next pulse. This is not an independent position or safety sensor.
- To enter USB download mode, hold BOOT, tap RST, then release BOOT. Keep MOTOR_EN/GPIO27 HIGH during download. After flashing, release BOOT and reset for normal operation.
- GPIO26 and GPIO27/28 are used as outputs after their boot values are latched. GPIO25 and GPIO3 are SDIO timing straps; the application does not use SDIO. GPIO7 can affect JTAG selection; no eFuse changes are required.
- GPIO15 is usable on the N4 module without in-package PSRAM, per the module datasheet. Do not use this map with an N4R2/N8R8 PSRAM module. The onboard D13 LED follows EM_CTRL; it does not prove magnet current or successful pickup.
- All external logic inputs must stay in the 3.3 V domain. Connect common ground. Keep the 74AHCT1G125/appropriate LED level conversion and the motor/MOSFET driver circuits; do not connect motor coils or the electromagnet directly to GPIO.
- Use the fixed **3V3** supply, not the default-OFF **3V3_C**, for sensor logic. Do not power motors or the magnet from the FireBeetle's 3.3 V rail. Connect the existing sensor PCB logic/pull-ups to 3.3 V as documented. Verify external supplies before connecting USB; do not tie conflicting regulator outputs together.
- The C5 is a wired replacement controller for a test harness. Do not drive the same signal simultaneously from a populated original MCU and the C5. Isolate the original controller's signal outputs first.

## Sensor Ribbon Contacts

| Original Master J4 / Sensor J1 contact | Net | C5 GPIO |
|---:|---|---:|
| 1 | DIG_OUT3 | 8 |
| 2 | DIG_OUT7 | 24 |
| 3 | DIG_OUT4 | 9 |
| 4 | DIG_OUT8 | 25 |
| 5 | DIG_OUT6 | 23 |
| 6 | DIG_OUT2 | 7 |
| 7 | DIG_OUT5 | 10 |
| 8 | DIG_OUT1 | 6 |
| 9 | LED_IN after external level conversion | 2 through buffer |
| 10 | GND | GND |
| 11 | MUX_IN1 | 3 |
| 12 | GND | GND |
| 13 | MUX_IN2 | 4 |
| 14 | +3V3 | Verified 3.3 V logic supply |
| 15 | MUX_IN3 | 5 |
| 16 | +5V | Verified external LED/buffer supply |

Sensor logic remains active-low (LOW = occupied). LM339 outputs are digital inputs, not ADC readings. Confirm a1/h1/a8/h8 and use POLARITY HIGH only if physical measurements require it. LEDs default to LED0=a1 with serpentine rows; row/column flips remain configurable in main/board_pins.h.

## Sources

- [DFRobot DFR1222 board overview and pinout](https://wiki.dfrobot.com/dfr1222/)
- [DFRobot V1.0 schematic](https://dfimg.dfrobot.com/wiki/20190/DFR1222_firebeetle-2-esp32-c5_schematics_V1.0.pdf)
- [ESP32-C5-WROOM-1/1U datasheet, pin table notes and boot configuration](https://documentation.espressif.com/esp32-c5-wroom-1_wroom-1u_datasheet_en.html)
- [ESP-IDF 5.5.3 C5 SoC capabilities](https://github.com/espressif/esp-idf/blob/v5.5.3/components/soc/esp32c5/include/soc/soc_caps.h)
