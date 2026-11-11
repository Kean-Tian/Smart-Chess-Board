# ESP32-S2-Saola-1 Bench Connections

Current controller: **ESP32-S2-Saola-1**, 4 MB Flash, PSRAM disabled. This is the current jumper-wire connection to Sensor PCB V2 and the driver boards. The retained original Master PCB schematic is not an S2 board design. Basic S2 USB communication and scan-frame generation have been tested; complete electrical, sensor-coordinate and actuator validation remains pending.

## Current GPIO Map

Use printed **GPIO numbers**, not connector positions or module pad numbers.

| Function / net | S2 GPIO | Role |
|---|---:|---|
| MUX_IN1 / A0 | 36 | Least-significant row-select bit; output |
| MUX_IN2 / A1 | 37 | Row-select bit; output |
| MUX_IN3 / A2 | 38 | Most-significant row-select bit; output |
| DIG_OUT1 | 1 | Digital sensor input; logical file a with current flags |
| DIG_OUT2 | 2 | Digital sensor input; logical file b |
| DIG_OUT3 | 3 | Digital sensor input; logical file c |
| DIG_OUT4 | 4 | Digital sensor input; logical file d |
| DIG_OUT5 | 5 | Digital sensor input; logical file e |
| DIG_OUT6 | 6 | Digital sensor input; logical file f |
| DIG_OUT7 | 7 | Digital sensor input; logical file g |
| DIG_OUT8 | 8 | Digital sensor input; logical file h |
| External RGB data into level shifter | 17 | Output; not the onboard RGB LED |
| Electromagnet control into driver | 12 | Output |
| X STEP / DIR | 14 / 21 | Outputs into motor driver |
| Y STEP / DIR | 15 / 16 | Outputs into motor driver |
| Shared motor enable | 13 | Active-low output; external 10k pull-up to 3.3 V |
| UART0 TX / RX | 43 / 44 | Reserved for onboard USB-UART bridge |

GPIO1..8 remain inputs with internal pull-up/down disabled. Use the sensor board's 3.3 V comparator pull-ups; never drive these inputs to force a reading. The firmware currently defaults to HIGH when occupied. Recheck polarity only after both PCB supply rails are present; the latest fault investigation found that only 3.3 V and GND had been connected.

## Sensor PCB V2 J1 Contacts

The user confirmed wiring **by DIG_OUT signal name**, not J1 contact number. The following order comes from the supplied `SCBSensorPCBV2.kicad_sch`; it replaces the older Sensor PCB ribbon table.

| J1 contact | Signal | S2 connection |
|---:|---|---|
| 1 | DIG_OUT2 | GPIO2 |
| 2 | DIG_OUT3 | GPIO3 |
| 3 | DIG_OUT1 | GPIO1 |
| 4 | DIG_OUT4 | GPIO4 |
| 5 | DIG_OUT6 | GPIO6 |
| 6 | DIG_OUT7 | GPIO7 |
| 7 | DIG_OUT5 | GPIO5 |
| 8 | DIG_OUT8 | GPIO8 |
| 9 | LED_IN | GPIO17 through the required level conversion |
| 10 | GND | Common ground |
| 11 | MUX_IN1 / A0 | GPIO36 |
| 12 | GND | Common ground |
| 13 | MUX_IN2 / A1 | GPIO37 |
| 14 | +3V3 | Verified sensor logic supply |
| 15 | MUX_IN3 / A2 | GPIO38 |
| 16 | +5V | Required supply for LM339 U3/U4 and the external LED/buffer rail |

## Required Sensor PCB Supply Rails

Sensor PCB V2 requires both rails: J1 contact14 (+3V3) powers the 74HC138 decoder and 74HC04 row-selection inverters; contact16 (+5V) powers LM339 comparators U3/U4 at their V+ pin3. J1 contacts10/12 are GND. A USB connection to the MCU does not automatically supply these PCB contacts.

In the latest troubleshooting session, only 3.3 V and GND were connected. The board displayed all occupied with HIGH polarity, then empty with LOW polarity but no magnet response. This does not validate either polarity: the missing comparator supply must be corrected before testing occupancy. Connect the intended +5V supply to the PCB power contact with common ground, not to GPIO1..8 or DIG_OUT signals. Keep the two supply rails separate. Verify physical connector numbering before powering up.

## Decoder and Logical Coordinate Mapping

U5 (74HC138) selects one of eight active-low row outputs. The following 74HC04 inverters supply the selected sensor row. Column signals pass through the sensor-board diode/comparator circuitry to DIG_OUT1..8.

| Address index | Printed MUX A2,A1,A0 | GPIO36,37,38 (A0,A1,A2) | Schematic sensors | Current logical rank |
|---:|---|---|---|---:|
| 0 | 000 | 000 | HE1–HE8 | 1 |
| 1 | 001 | 100 | HE9–HE16 | 2 |
| 2 | 010 | 010 | HE17–HE24 | 3 |
| 3 | 011 | 110 | HE25–HE32 | 4 |
| 4 | 100 | 001 | HE33–HE40 | 5 |
| 5 | 101 | 101 | HE41–HE48 | 6 |
| 6 | 110 | 011 | HE49–HE56 | 7 |
| 7 | 111 | 111 | HE57–HE64 | 8 |

`INPUTS(DIG_OUT1..8)` is printed in signal order: `10000000` means DIG_OUT1 is HIGH, and `00000001` means DIG_OUT8 is HIGH. It is not a conventional most-significant-bit-first binary number.

With both sensor orientation flags zero, address 000 / DIG_OUT8 maps to logical `h1` and schematic sensor HE8. **It does not establish a physical top-right corner.** The user reported that this sensor was at the physical lower-left in the tested board placement. Four-corner and complete-grid calibration are still required. Keep electrical mapping, schematic placement and physical viewing direction separate. LED orientation has independent flags and also requires testing.

## USB and Electrical Constraints

- The board Micro-USB connector uses the onboard USB-UART bridge and GPIO43/44 at 115200 baud, 8N1. GPIO1/3 are ordinary sensor inputs on this S2 map. Native USB pins GPIO19/20 are unused.
- GPIO46 cannot drive a MUX output. GPIO0/45/46 are excluded from the harness; GPIO22–25 do not exist on S2 and GPIO26–32 are excluded for module memory. GPIO18 is the onboard RGB LED and is unused.
- Connect logic grounds. Use 3.3 V logic. Keep external motor, magnet and LED power on the intended driver supplies; never drive a coil directly from a GPIO.
- Add the motor-enable pull-up before actuator tests. Avoid connecting independent regulator outputs together or attaching the replacement controller to another MCU's active outputs.
- For manual download, hold BOOT, press/release RESET, then release BOOT when esptool connects. Close serial clients before flashing. See the [S2 test guide](ESP32_S2_Test_Guide.md).

## References

- [Supplied Sensor PCB V2 schematic](../hardware/reference/SCBSensorPCBV2.kicad_sch)
- [Espressif Saola-1 board guide and header table](https://docs.espressif.com/projects/esp-idf/en/v5.1/esp32s2/hw-reference/esp32s2/user-guide-saola-1-v1.2.html)
- [Espressif ESP32-S2 GPIO reference](https://docs.espressif.com/projects/esp-idf/en/v5.1/esp32s2/api-reference/peripherals/gpio.html)
- `esp32/main/board_pins.h` is the current firmware pin definition.
