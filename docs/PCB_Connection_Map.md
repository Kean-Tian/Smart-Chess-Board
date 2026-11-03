# WeMos LOLIN32 Bench Connections

Current target: **WeMos LOLIN32 V1.0.0, ESP-WROOM-32 / classic ESP32**, 4 MB Flash, no PSRAM. This follows the exact pinout supplied by the user and the WEMOS V1.0.0 schematic linked there. It is a proposed jumper-wire controller for the existing sensor/driver boards, not the copper routing of the earlier Master PCB. Pin assignments and firmware have not been validated on connected hardware.

## GPIO and UART Mapping

Use the GPIO labels on the pinout. Adjacent chip/package pin numbers are not GPIO numbers and are not breadboard header indices.

| Existing function / net | LOLIN32 GPIO | Board label / role |
|---|---:|---|
| LED_IN_3V3 into external 74AHCT1G125 | 4 | 4; external RGB data |
| MUX_IN1 / row A0 | 16 | 16 / RX2; row address, not UART2 |
| MUX_IN2 / row A1 | 17 | 17 / TX2; row address, not UART2 |
| MUX_IN3 / row A2 | 18 | 18; row address |
| DIG_OUT1 / file a | 36 | VP; input only |
| DIG_OUT2 / file b | 39 | VN; input only |
| DIG_OUT3 / file c | 34 | 34; input only |
| DIG_OUT4 / file d | 35 | 35; input only |
| DIG_OUT5 / file e | 32 | 32; digital input |
| DIG_OUT6 / file f | 33 | 33; digital input |
| DIG_OUT7 / file g | 25 | 25; digital input |
| DIG_OUT8 / file h | 26 | 26; digital input |
| EM_CTRL into external MOSFET driver | 27 | 27 |
| X_STEP into A4988 | 19 | 19 |
| X_DIR into A4988 | 21 | 21 |
| Y_STEP into A4988 | 22 | 22 |
| Y_DIR into A4988 | 23 | 23 |
| MOTOR_EN, shared active-low A4988 enable | 13 | 13; add external 10k pull-up to 3.3 V |
| UART0 TX | 1 | TX; already connected to onboard USB-UART bridge |
| UART0 RX | 3 | RX; already connected to onboard USB-UART bridge |

The map uses 18 external control/sensor signals plus UART0 TX/RX. GPIO14 remains spare. GPIO0/2/5/12/15 are excluded from the external harness because they are boot straps. GPIO6-11 are reserved for Flash. GPIO24 and GPIO28 do not exist on this classic ESP32 pinout. GPIO34/35/36/39 are never configured as outputs.

## USB Connection and Pin Restrictions

- Use the board's **Micro-USB data connector**. The WEMOS V1.0.0 schematic uses a CP2104 USB-UART bridge connected to GPIO1/GPIO3. The ESP32 does not have the native USB Serial/JTAG peripheral used by the previous firmware target.
- The application uses UART0 at **115200 baud, 8N1, no hardware flow control**. The baud rate must match the host. Leave the TX/RX header pins free and do not attach another active UART transmitter to them.
- Linux commonly assigns `/dev/ttyUSB0`; macOS may use `/dev/cu.SLAB_USBtoUART` or `/dev/cu.usbserial-*`. Use the actual port from `python -m serial.tools.list_ports -v`. A clone may use a different USB-UART chip or connector, so check its physical labels before wiring.
- GPIO34-39 have no internal pull-up/down. Use the sensor board's external **3.3 V pull-ups** for all LM339 digital outputs. These are digital occupancy inputs, not ADC readings. Never apply 5 V logic to them.
- GPIO16/17 are available on the specified WROOM board without PSRAM. This map is not for a WROVER/PSRAM board.
- The onboard user LED is active-low GPIO5; it is not mapped to the magnet or external RGB commands. The previous MAGNET/onboard-D13 light test does not apply. PING/STATUS are the USB-only checks; use an external RGB chain for LED commands.
- Add the **10k MOTOR_EN/GPIO13 pull-up** before connecting motor drivers. It keeps them disabled while the chip is reset, unpowered, or being flashed. Firmware sets EN HIGH and EM_CTRL LOW before normal control starts. Keep actuator power disabled during flashing.
- Connect common ground between logic and driver supplies. Do not directly drive coils or the electromagnet from GPIO. Keep the external A4988/MOSFET driver and RGB level shifter. Power motors/magnet/LEDs from appropriate external supplies, not the LOLIN32 3.3 V rail.
- If the existing PCB already supplies 3.3 V, do not tie two independent regulator outputs together. Check the intended supply and common reference before connecting USB. Isolate any populated original MCU outputs before attaching this replacement harness.
- This board has EN/RESET and GPIO0-based download circuitry, not the FireBeetle GPIO28 BOOT arrangement. If auto-download fails, use an appropriate GPIO0-to-GND download jumper while resetting EN, then release GPIO0 after flashing. Do this with external actuator power off. No eFuse changes or force-flashing are required.

## Existing Sensor Ribbon Contacts

| Master J4 / Sensor J1 contact | Net | LOLIN32 GPIO |
|---:|---|---:|
| 1 | DIG_OUT3 | 34 |
| 2 | DIG_OUT7 | 25 |
| 3 | DIG_OUT4 | 35 |
| 4 | DIG_OUT8 | 26 |
| 5 | DIG_OUT6 | 33 |
| 6 | DIG_OUT2 | 39 |
| 7 | DIG_OUT5 | 32 |
| 8 | DIG_OUT1 | 36 |
| 9 | LED_IN after external level conversion | 4 through buffer |
| 10 | GND | GND |
| 11 | MUX_IN1 | 16 |
| 12 | GND | GND |
| 13 | MUX_IN2 | 17 |
| 14 | +3V3 | Verified sensor logic supply |
| 15 | MUX_IN3 | 18 |
| 16 | +5V | Verified external LED/buffer supply |

The ribbon contact order is not DIG_OUT1,2,3... . Default LOW means occupied. Confirm a1/h1/a8/h8 before gameplay. LED0 defaults to a1 with serpentine rows. Orientation flips remain in main/board_pins.h.

## Sources

- [User-specified LOLIN32 pinout](https://mischianti.org/esp32-wemos-lolin32-high-resolution-pinout-and-specs/)
- [WEMOS LOLIN32 V1.0.0 schematic, mirrored with that pinout](https://mischianti.org/wp-content/uploads/2023/11/schematic_wemos_lolin32_v1.0.0.pdf)
- [Espressif ESP32-WROOM-32 datasheet](https://documentation.espressif.com/esp32-wroom-32_datasheet_en.html)
- [Espressif GPIO restrictions](https://docs.espressif.com/projects/esp-idf/en/v5.5.3/esp32/api-reference/peripherals/gpio.html)
- [ESP-IDF UART API](https://docs.espressif.com/projects/esp-idf/en/v5.5.3/esp32/api-reference/peripherals/uart.html)
