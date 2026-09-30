# Raspberry Pi Pico 2 firmware

This Pico SDK application targets `PICO_BOARD=pico2`. It runs the MCU controller
in button-test mode, uses the external push button on GP2 (active low with the
internal pull-up), reports events on UART0 at 115200 8-N-1, and drives the
Pico 2 onboard LED as the pending-move indicator.

## Build UF2

Install the Raspberry Pi Pico SDK and toolchain, set `PICO_SDK_PATH`, then run:

```sh
cmake -S firmware/pico -B build-pico
cmake --build build-pico
```

Flash `build-pico/scb_pico2.uf2` to the Pico 2 using BOOTSEL/USB. BOOTSEL is a
bootloader control and is not used as the application test button.

## UART wiring to Raspberry Pi 4 Model B

- Pico 2 UART0 TX (default GP0) -> Pi GPIO15 UART RX (40-pin header pin 10)
- Pico 2 UART0 RX (default GP1) <- Pi GPIO14 UART TX (40-pin header pin 8)
- Pico GND -> Pi GND
- External momentary switch between Pico GP2 and GND

Both boards use 3.3 V UART logic. Do not connect a 5 V UART signal. The Pico
firmware currently simulates Hall-square changes with the push button; direct
64-sensor scanning needs the final multiplexer/shift-register hardware design.
