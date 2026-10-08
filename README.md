# Raspberry Pi 5 Sensor Matrix Interface

This component provides the following functionality:

1. Configures the Raspberry Pi 5 GPIO pins.
2. Selects eight sensor rows through a 74HC138 and reads eight LM324 outputs directly.
3. Scans the complete 8×8 Hall-sensor matrix with square mapping, settling delays, and debouncing.
4. Detects piece lifts, returns, placements, normal moves, and captures.
5. Prints sensor status and detected moves in the terminal.
6. Provides automated tests and a physical-hardware test procedure.

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

## Automated tests

The sensor-matrix tests do not require GPIO hardware:

```sh
cmake -S . -B build
cmake --build build
./build/sensor_matrix_tests
```

The tests cover the 74HC138 address sequence, simultaneous active columns,
64-square mapping, comparator polarity, debouncing, lift and return detection,
normal moves, and captures.

To demonstrate the behavior without a Raspberry Pi or sensor board, run:

```sh
cmake -S . -B build
cmake --build build --target sensor_matrix_demo
./build/sensor_matrix_demo
```

This C program prints the eight row addresses, separate column readings, the
three-read debounce sequence, and terminal events for placement, lift, return,
normal movement, and capture. It uses simulated GPIO; it does not validate the
physical wiring, voltage levels, comparator threshold, or sensor timing.

Run all configured tests with:

```sh
ctest --test-dir build --output-on-failure
```

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
