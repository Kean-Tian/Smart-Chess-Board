# PCB V2 Connection Map

Source: the user-supplied `SCBMasterPCBV2.zip` and `SCBSensorPCBV2 (1).zip`, inspected 2026-11-23 using KiCad XML netlists and PCB pad nets. Evidence and source SHA-256 values are in [connections.json](../hardware/pcb_v2/connections.json). QFN pad numbers are not GPIO numbers.

## Cable: straight IDC16, pin n to pin n

Master J4 and sensor J1 do NOT put every matching signal name on the same contact. Firmware remaps the sensor inputs and address bits to compensate; do not connect by label name with this default.

| Sensor function | Sensor J1 contact | Master J4 net on that contact | S3 GPIO |
|---|---:|---|---:|
| Sensor A0 / MUX_IN1 | 11 | MUX_IN3 | 6 |
| Sensor A1 / MUX_IN2 | 13 | MUX_IN2 | 5 |
| Sensor A2 / MUX_IN3 | 15 | MUX_IN1 | 4 |
| DIG_OUT1 / column 1 | 3 | DIG_OUT7 | 13 |
| DIG_OUT2 / column 2 | 1 | DIG_OUT8 | 14 |
| DIG_OUT3 / column 3 | 2 | DIG_OUT4 | 10 |
| DIG_OUT4 / column 4 | 4 | DIG_OUT3 | 9 |
| DIG_OUT5 / column 5 | 7 | DIG_OUT5 | 11 |
| DIG_OUT6 / column 6 | 5 | DIG_OUT6 | 12 |
| DIG_OUT7 / column 7 | 6 | DIG_OUT2 | 8 |
| DIG_OUT8 / column 8 | 8 | DIG_OUT1 | 7 |
| LED data after level shifter | 9 | LED_IN | 2, before U5 74AHCT1G125 |
| GND | 10, 12 | GND | Common ground |
| Sensor logic supply | 14 | +3V3 | Power, not GPIO |
| Comparators and LEDs | 16 | +5V | Power, not GPIO |

`SCB_COLUMN_PINS` is sensor DIG_OUT1..8 order, not master label order. `SENSOR inputs=` remains in sensor column order. A name-crossed custom harness requires `CONFIG_SCB_SENSOR_NAMED_WIRING=y`; that is not the selected straight-cable connection.

## Main outputs and communication

| Function | Schematic GPIO | PCB pad-net GPIO |
|---|---:|---:|
| LED_IN_3V3 | 2 | 2 |
| EM_CTRL (active HIGH) | 33 | 33 |
| X_STEP | 34 | 35 |
| X_DIR | 35 | 34 |
| Y_STEP | 36 | 37 |
| Y_DIR | 37 | 36 |
| MOTOR_EN (both drivers, active LOW) | 38 | 38 |
| Native USB D- / D+ | 19 / 20 | 19 / 20 |
| J6 TX / RX | 18 / 17 | 18 / 17 |

**The four motor assignments differ between the supplied schematic and PCB.** The user confirmed fabrication from the supplied PCB. The selected default is `CONFIG_SCB_MOTOR_PCB_ROUTING=y`: X STEP=35/DIR=34 and Y STEP=37/DIR=36. Disable this option only for hardware wired according to the conflicting schematic. Record the selected variant in the release manifest and verify before powering actuators. Software cannot determine which copper was manufactured.

J5 is native USB-B, not a CP210x bridge. J5 VBUS contact 1 is explicitly unconnected: USB does not power the board. Supply the PCB through its intended external power input. J6 is a 3.3 V application UART1; cross Pi TX to J6 RX and Pi RX to J6 TX with common ground. ROM UART0 pins 43/44 are unconnected, so J6 does not provide the usual ROM UART flashing path. Use J5 native USB and BOOT/RESET for initial flashing.

## Sensor and LED coordinates

The sensor decoder is 74HC138: selected output is inverted by 74HC04 to power one row of eight DRV5053 sensors. Settling remains 1 ms and complete scans target 10 ms, with two identical whole-board snapshots. The comparators are LM339, powered from 5 V, with 4.7k output pull-ups to 3.3 V. The reference divider R18=100k/R19=82k gives about 1.49 V at nominal 3.3 V; it is not a software threshold. Magnet orientation and real voltage margins must be measured.

Logical reference is HE1=a1, HE8=h1, HE57=a8, HE64=h8. This is an indexing convention, not a claim about the observer's physical corner. Verify four corners/all squares on the assembled board. The LED chain is DL1..DL8, DL16..DL9, DL17..DL24, etc., matching the existing serpentine mapping; all 64 indices are checked against the netlist. Both orientation flags remain zero. Do not silently mask an empty-board false positive.

## Electrical limitations

The row inverter directly supplies eight Hall devices; verify row voltage/current and startup at the PCB rather than assuming software settling fixes supply droop. No endstop/home input or temperature sensor is connected in these schematics. HOME therefore continues returning NO_HOME_SWITCHES. A4988 MS1/MS2/MS3 are grounded (full steps); phase current is set in hardware, not by firmware. Motor direction, CoreXY coefficients, steps/mm and carriage reference are mechanical calibrations and are not inferred from net names.
