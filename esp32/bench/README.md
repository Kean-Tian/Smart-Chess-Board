# Optional ESP32-S2 Fixed-MUX Tests

These small ESP-IDF projects use the shared `../main/board_pins.h` S2 map. They replace the main application when flashed. Neither performs full-board scanning, runs the game, or exercises motors/magnet. The normal scanner changes MUX levels continuously, so use these only to measure a fixed address with a multimeter or logic analyzer.

| Project | Application output | UART behavior |
|---|---|---|
| `gpio_low/` | GPIO36/37/38 = 000, decoder address 000 | No SCB UART commands; PING will time out |
| `gpio_a0_high/` | GPIO36/37/38 = 100, decoder address 001 | PING, STATUS, INPUTS, STOP/DISARM; SCAN/RAW return SCAN_DISABLED_FIXED_A0 |

The A0 test follows current A0=GPIO36, not the earlier GPIO38 assignment. A1/A2 are explicitly LOW. STATUS identifies the mode and actual GPIO levels. STOP does not change the fixed address; outputs remain at the test values. GPIO1..8 remain inputs. Motor enable is HIGH and magnet/step outputs are LOW after application initialization. Reset/ROM states are outside the application's control.

With ESP-IDF 5.5.3 active, change to either project and run:

```sh
idf.py set-target esp32s2
idf.py build
idf.py -p PORT flash
```

Use the flash addresses generated for that project. Do not package these images into the main `esp32/release/` directory. The main release helper intentionally flashes the main scanner, not these bench images. Compilation does not mean the revised bench firmware has been tested on hardware.

**Restore full scanning afterward** by flashing the main release from the project root:

```sh
esp32/.venv/bin/python esp32/scripts/flash_firmware.py --port PORT --baud 57600 --no-compress
```

Then open the main terminal and verify PING, SCAN and the `SCB_S2_SAOLA_1` identifier. Keep actuator power disconnected during fixed-MUX tests and flashing.
