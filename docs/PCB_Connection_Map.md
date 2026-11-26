# Master PCB V3 + Sensor PCB V2.2 Connection Map

Sources: the top-level current files in `SCBMasterPCBV3.zip` and `SCBSensorPCBV2.2.zip`, inspected 2026-11-24. The `_restore_backup_...` schematic in the master ZIP is historical and excluded. Source SHA-256 values, exported net assignments and all 64 LED connections are recorded in [connections.json](../hardware/pcb_v3/connections.json). MCU/connector pad nets agree between the supplied current schematics and PCB files. GPIO numbers are not QFN pad numbers.

## Straight IDC16 cable: master J4.n to sensor J1.n

Master and sensor DIG_OUT labels now agree. MUX_IN1 and MUX_IN3 still occupy opposite contacts, so firmware compensates the address order.

| Sensor function | J1 / J4 contact | Master net | S3 GPIO |
|---|---:|---|---:|
| A0 / MUX_IN1 | 11 | MUX_IN3 | 10 |
| A1 / MUX_IN2 | 13 | MUX_IN2 | 9 |
| A2 / MUX_IN3 | 15 | MUX_IN1 | 8 |
| DIG_OUT1 | 3 | DIG_OUT1 | 13 |
| DIG_OUT2 | 1 | DIG_OUT2 | 14 |
| DIG_OUT3 | 2 | DIG_OUT3 | 4 |
| DIG_OUT4 | 4 | DIG_OUT4 | 5 |
| DIG_OUT5 | 7 | DIG_OUT5 | 11 |
| DIG_OUT6 | 5 | DIG_OUT6 | 12 |
| DIG_OUT7 | 6 | DIG_OUT7 | 6 |
| DIG_OUT8 | 8 | DIG_OUT8 | 7 |
| LED data | 9 | LED_IN after U5 level shifter | 21 before U5 |
| Common GND | 10, 12 | GND | Power return |
| Sensor logic power | 14 | +3V3 | Not GPIO |
| Comparator/LED power | 16 | +5V | Not GPIO |

`SCB_COLUMN_PINS` is sensor DIG_OUT1..8 order. Native protocol SENSOR input bits follow that order. A verified custom cable crossed by MUX signal names requires `CONFIG_SCB_SENSOR_NAMED_WIRING=y` (A0/A1/A2 then use GPIO8/9/10); this is not the default straight cable.

## Outputs and communication

| Function | S3 GPIO | Notes |
|---|---:|---|
| LED data | 21 | U5 74AHCT1G125 to J4.9 |
| Electromagnet | 33 | EM_CTRL, active HIGH |
| X STEP / DIR | 35 / 34 | Schematic and PCB agree |
| Y STEP / DIR | 37 / 36 | Schematic and PCB agree |
| Both motor enables | 38 | Active LOW |
| GPIO46 PCB test | 46 | QFN pad 52, D6 anode; D6 cathode through R17 680 ohm to GND |
| J5 native USB D- / D+ | 19 / 20 | USB Serial/JTAG, not a CP210x bridge |
| J6 UART1 TX / RX | 17 / 18 | J6.1 TX, J6.2 RX, J6.3 GND |

The main firmware preloads GPIO46 HIGH, then enables its output after application startup. D6 should illuminate if assembled and electrically correct. Firmware does not control reset/download strapping levels; do not externally force GPIO46 HIGH during download entry. This is a requested persistent test output, not a sensor-select pin.

J5 VBUS is connected to U6 ESD protection and C31, not to the system +5V rail. USB alone does not power the board: use the intended external supply. Initial programming uses J5 native USB and BOOT/RESET. J6 is a 3.3 V application UART1, not ROM UART0; the ROM pins GPIO43/44 remain unconnected. For wired UART, cross host TX to J6 RX and host RX to J6 TX with common ground.

## Sensing and physical verification

The decoder remains 74HC138 followed by 74HC04 row power inversion, with DRV5053 sensors and LM339 comparators. LM339 power is 5 V; its outputs have 4.7k pull-ups to 3.3 V. R18=100k/R19=82k produce about 1.49 V reference from nominal 3.3 V. Firmware observes digital levels and cannot adjust that analog threshold. HIGH occupancy is the initial default; verify with the actual magnets and an empty board.

Nominal full scans remain 10 ms / 100 Hz with 1 ms row settling and two matching complete frames. These are software targets, not new hardware measurements. The row inverter directly supplies eight sensors; verify voltage/current margins when diagnosing false occupancy.

Logical indexing remains HE1=a1, HE8=h1, HE57=a8, HE64=h8; verify the assembled viewing direction and every square. The 64-LED chain retains serpentine ordering. No automatic polarity/orientation correction or false-positive masking is applied.

No home switches or temperature inputs are connected. HOME continues returning NO_HOME_SWITCHES. Step scale, direction, CoreXY calibration, driver phase current and reliable piece transport require real hardware tests and are not inferred from GPIO names.
