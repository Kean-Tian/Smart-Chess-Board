# Raspberry Pi 4 UART bridge

`scb_pi_uart_bridge` reads line-based events from `/dev/serial0` at 115200 baud.
It prints sensor changes and applies `SCB1 MOVE <from> <to>` events to the
existing chess-rules model, rejecting moves that are illegal in the current game.

## Build on Raspberry Pi OS

From the repository root:

```sh
cmake -S . -B build
cmake --build build --target scb_pi_uart_bridge
./build/scb_pi_uart_bridge /dev/serial0
```

Enable the Pi serial hardware and disable the serial login shell in
`raspi-config` under Interface Options > Serial Port. The device path may be
`/dev/serial0`; confirm it on the target OS before running.
