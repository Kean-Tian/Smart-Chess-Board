# Raspberry Pi 5 Sensor Matrix Interface

This component provides the following functionality:

1. Configures the Raspberry Pi 5 GPIO pins.
2. Selects eight sensor rows through a 74HC138 and reads eight LM324 outputs directly.
3. Scans the complete 8×8 Hall-sensor matrix with square mapping, settling delays, and debouncing.
4. Detects piece lifts, returns, placements, normal moves, and captures.
5. Prints sensor status and detected moves in the terminal.
6. Provides a physical-hardware test procedure.

## Software architecture

The hardware program processes the sensor data in the following order:

```text
Configure three address outputs and eight comparator inputs
                         |
                         v
Select one row with the 74HC138 and read all eight columns
                         |
                         v
Repeat for all eight rows to create one 64-square snapshot
                         |
                         v
Require three identical snapshots before accepting a stable state
                         |
                         v
Compare the new stable state with the previous stable state
                         |
                         v
Print READY, LIFT, RETURN, PLACE, MOVE, or WAIT PLACE
```

The implementation is divided into three main source files:

| File | Responsibility |
| --- | --- |
| `include/scb/sensor_matrix.h` | Declares the matrix, debounce, GPIO-operation, and movement-event data structures. |
| `src/sensor_matrix.c` | Implements pin defaults, validation, row scanning, square mapping, debouncing, and movement detection. |
| `src/hardware_main.c` | Uses libgpiod to configure the real Pi GPIO lines, repeatedly runs the processing pipeline, and prints events. |

### 1. GPIO configuration

`scb_sensor_matrix_defaults()` defines three BCM GPIO numbers for the 74HC138
address inputs and eight BCM GPIO numbers for the LM324 outputs. The assignments
are project choices, not requirements imposed by the decoder, and can be
overridden from the command line.

`backend_open()` in `src/hardware_main.c` requests the three address lines as
outputs and the eight comparator lines as inputs through libgpiod. The program
uses BCM GPIO numbers internally; the physical-pin column in the table below is
only for locating each signal on the 40-pin header.

`scb_sensor_matrix_validate()` rejects missing GPIO operations, out-of-range
GPIO numbers, and assignments that reuse one GPIO for more than one signal.

### 2. 74HC138 row addressing

`scb_sensor_matrix_scan()` cycles `row` from 0 through 7. For each row, it
extracts three bits from the row number and writes them to A0, A1, and A2:

```text
row 0 -> A2A1A0 = 000 -> Y0
row 1 -> A2A1A0 = 001 -> Y1
row 2 -> A2A1A0 = 010 -> Y2
row 3 -> A2A1A0 = 011 -> Y3
row 4 -> A2A1A0 = 100 -> Y4
row 5 -> A2A1A0 = 101 -> Y5
row 6 -> A2A1A0 = 110 -> Y6
row 7 -> A2A1A0 = 111 -> Y7
```

The current schematic permanently enables the 74HC138: active-low enable pins
4 and 5 are tied to GND, and active-high enable pin 6 is tied to +5 V. The Pi
therefore controls only A0, A1, and A2. There is no software-controlled row
enable pin.

### 3. Eight independent comparator inputs

After selecting a row, `backend_read_columns()` reads `ENC_IN1` through
`ENC_IN8` separately. These values represent files `a` through `h` for the
currently selected row. Reading eight independent inputs preserves multiple
occupied columns in the same row.

The 74LS147 priority encoder is bypassed. A priority encoder reports only its
highest-priority active input and would therefore lose occupancy information
when two or more columns are active simultaneously.

### 4. Complete 8x8 scan and storage

One call to `scb_sensor_matrix_scan()` selects all eight rows and reads eight
columns per row. It stores the result in a 64-element Boolean array named
`occupied`, where `true` means occupied and `false` means empty according to the
configured comparator polarity.

The array index is calculated as:

```text
index = row * 8 + column
```

For example, `e2` has zero-based row 1 and zero-based column 4, so its index is
`1 * 8 + 4 = 12`. The current mapping places `a1` at index 0 and `h8` at index
63. The physical orientation must still be confirmed on the assembled board.

`scb_square_index()` converts a name such as `e2` to an array index, while
`scb_square_name()` performs the reverse conversion for terminal messages.

### 5. Settling delays

Immediately reading the inputs after changing A0/A1/A2 could capture a signal
while the decoder, sensor line, or comparator output is still changing.
`scb_sensor_matrix_scan()` therefore applies two delays before reading each row:

- `address_settle_us`, default 10 microseconds, after changing the decoder address.
- `sensor_settle_us`, default 1000 microseconds, before sampling the columns.

These are initial software values. The final values must be calibrated using
measurements from the physical sensor board.

### 6. Three-scan debouncing

`scb_debouncer_update()` compares each new 64-square snapshot with a candidate
snapshot. An identical result increments `candidate_count`; a different result
replaces the candidate and resets the count to one. The default configuration
publishes a new stable board only after three identical complete snapshots.

A stable state that is identical to the previously published state is ignored,
so an unchanged board does not repeatedly produce events. Debouncing the whole
snapshot prevents a single short sensor disturbance from immediately producing
a false lift or move.

### 7. Piece-event detection

`scb_move_tracker_process()` compares the new stable snapshot with the previous
stable snapshot:

- Occupied to empty records a lift and produces `LIFT e2`.
- Empty to occupied with no pending lift produces `PLACE e4`.
- A lifted piece returning to the same square produces `RETURN e2`.
- A lifted piece appearing on another square produces `MOVE e2e4`.
- For a basic capture, the captured piece is removed, the moving piece is
  lifted, and the moving piece is placed on the destination square. For example,
  this sequence can produce `MOVE e4d5`.

Lifted squares are stored in `pending_lifts` until the program observes a
placement. If multiple lifted squares make the result incomplete, the program
can print `WAIT PLACE` and continue waiting for a stable destination.

This module detects occupancy changes only. It does not identify piece types or
decide whether a chess move is legal.

### 8. Runtime loop and terminal output

`main()` in `src/hardware_main.c` repeatedly calls:

1. `scb_sensor_matrix_scan()` to obtain a raw 64-square snapshot.
2. `scb_debouncer_update()` to publish only stable changes.
3. `scb_move_tracker_process()` to interpret the stable change.
4. `puts()` to print the resulting event message.

The loop waits `poll_ms`, default 20 milliseconds, after each complete scan. It
runs until it receives `SIGINT` or `SIGTERM`; pressing Ctrl-C stops the loop and
releases the GPIO lines.

### 9. Runtime configuration

The executable accepts command-line options for the GPIO chip, address pins,
column pins, address delay, sensor delay, polling interval, debounce count, and
comparator polarity. This allows physical calibration without rewriting the
scanning algorithm. Run `./build/scb_hardware --help` to display all options.

## GPIO pin assignment

The program uses BCM GPIO numbering:

| Circuit signal | BCM GPIO | Physical pin | Direction |
| --- | ---: | ---: | --- |
| 74HC138 A0 / MUX_IN1 | GPIO17 | 11 | Output |
| 74HC138 A1 / MUX_IN2 | GPIO27 | 13 | Output |
| 74HC138 A2 / MUX_IN3 | GPIO22 | 15 | Output |
| LM324 ENC_IN1 / file a | GPIO5 | 29 | Input |
| LM324 ENC_IN2 / file b | GPIO6 | 31 | Input |
| LM324 ENC_IN3 / file c | GPIO12 | 32 | Input |
| LM324 ENC_IN4 / file d | GPIO13 | 33 | Input |
| LM324 ENC_IN5 / file e | GPIO16 | 36 | Input |
| LM324 ENC_IN6 / file f | GPIO19 | 35 | Input |
| LM324 ENC_IN7 / file g | GPIO20 | 38 | Input |
| LM324 ENC_IN8 / file h | GPIO21 | 40 | Input |

In the schematic, the 74HC138 active-low enable inputs (pins 4 and 5) are tied
to GND and its active-high enable input (pin 6) is tied to +5 V. The Pi drives
only A0, A1, and A2; GPIO23 is unused. Y0 maps to board rank 1 and Y7 maps to
rank 8.
COL1 maps to file `a`, and COL8 maps to file `h`. The first matrix element is
therefore `a1`, and the last element is `h8`.

## Electrical requirements

- The schematic uses a **74HC138** powered from 5 V. Its A0/A1/A2 inputs need
  guaranteed 5 V logic highs. Add a suitable 3.3 V-to-5 V logic buffer between
  the Pi and those inputs; direct 3.3 V drive is not guaranteed by the HC
  input specifications.
- Connect LM324 outputs `ENC_IN1` through `ENC_IN8` individually to the eight
  configured Pi inputs, after 3.3 V level protection. Do not feed the Pi from
  the 74LS147 priority encoder: it loses information when multiple columns
  are active at once.
- The LM324 compares each `HE_COL` voltage against the circuit's 1.5 V
  reference. The Pi reads the resulting digital levels; there is no Pi ADC or
  software voltage threshold. Because the reference is on the noninverting
  input, an `HE_COL` voltage below 1.5 V should drive the output high, subject
  to the LM324's output limits. Which magnetic pole produces that voltage must
  be confirmed on the assembled sensor board.
- Raspberry Pi GPIO inputs are not 5 V tolerant. If an LM324 is powered from
  5 V, its output must not connect directly to a Pi GPIO. Use reliable 3.3 V
  level conversion, or use open-collector comparators pulled up to 3.3 V.
- The Raspberry Pi, 74HC138, sensors, and comparators must share a common ground.

## Raspberry Pi setup

Install the compiler, CMake, and libgpiod development files:

```sh
sudo apt update
sudo apt install cmake build-essential pkg-config libgpiod-dev gpiod git
```

Identify the GPIO chip associated with the RP1 controller:

```sh
gpiodetect
```

The default user normally has GPIO access. If another account needs access, add
it to the `gpio` group and then log in again:

```sh
sudo usermod -aG gpio "$USER"
```

## Build and run

Build the project:

```sh
cmake -S . -B build
cmake --build build
```

Run the sensor interface using `/dev/gpiochip0` and the default pins:

```sh
./build/scb_hardware
```

Common configuration examples:

```sh
# A low comparator output means that the square is occupied.
./build/scb_hardware --columns-active-low

# Increase the sensor settling delay to 2 ms.
./build/scb_hardware --sensor-settle-us 2000

# Use a different GPIO chip.
./build/scb_hardware --gpiochip /dev/gpiochip4

# Override the GPIO assignments.
./build/scb_hardware \
  --address-pins 17,27,22 \
  --column-pins 5,6,12,13,16,19,20,21
```

The default configuration waits 1 ms after selecting each sensor row and waits
20 ms after every complete matrix scan. A new board state is accepted only
after three identical 64-square scans.

The default software interpretation is `ENC_IN` high = occupied. If your
measured comparator polarity is the opposite, run with `--columns-active-low`.

Terminal messages include:

- `LIFT e2`: a piece was lifted from e2.
- `RETURN e2`: the piece was returned to e2.
- `PLACE e4`: a piece was placed directly on e4.
- `MOVE e2e4`: a move from e2 to e4 was detected.

Hall sensors report occupancy only; they cannot identify piece types. During a
capture, the destination square must be observed empty for at least one stable
scan. Otherwise, the destination cannot be determined from final occupancy alone.

## Physical hardware test procedure

1. With the Pi disconnected, measure all eight comparator outputs and verify
   that they never exceed 3.3 V.
2. Start with an empty board and confirm that the terminal reports
   `READY 0 PIECES`.
3. Place one piece on `a1`, `h1`, `a8`, and `h8` to verify board orientation.
4. Test every square to confirm that all 64 sensors are detected reliably.
5. Test lift, return, placement, normal-move, and capture sequences.
6. If readings are unstable, increase `--sensor-settle-us` or
   `--debounce-reads`.

The final calibration and physical tests must be completed after the sensor
board is connected to the Raspberry Pi 5.
