#ifndef SCB_BOARD_PINS_H
#define SCB_BOARD_PINS_H

/* DFRobot DFR1222 V1.0, ESP32-C5-WROOM-1-N4 (no PSRAM).
 * Numbers are native GPIO numbers, NOT Arduino D numbers or module-pad numbers.
 * This is a jumper-wire test mapping; see docs/PCB_Connection_Map.md.
 */
#define SCB_PIN_LED 2
#define SCB_PIN_ROW_A0 3
#define SCB_PIN_ROW_A1 4
#define SCB_PIN_ROW_A2 5
#define SCB_COLUMN_PINS {6, 7, 8, 9, 10, 23, 24, 25}
#define SCB_PIN_MAGNET 15 /* D13/onboard LED; available on the N4/no-PSRAM module. */
#define SCB_PIN_X_STEP 12 /* RX: no UART console is enabled by the application. */
#define SCB_PIN_X_DIR 11  /* TX: ROM boot messages are harmless only with EN held HIGH. */
#define SCB_PIN_Y_STEP 26
#define SCB_PIN_Y_DIR 28  /* BOOT: open-drain output, using the board's pull-up. */
#define SCB_PIN_MOTOR_EN 27 /* Shared A4988 enable, LOW = enabled; external 10k pull-up required. */
#define SCB_PIN_USB_DM 13
#define SCB_PIN_USB_DP 14
#define SCB_GPIO_COUNT 29U

/* Keep GPIO0 (3V3_C power control) and GPIO1 (battery ADC) untouched.
 * GPIO26/27/28 are boot straps: never drive 27/28 LOW during reset.
 * Do not press BOOT while using the motion outputs.
 */
#define SCB_SENSOR_REVERSE_ROWS 0
#define SCB_SENSOR_REVERSE_COLUMNS 0
#define SCB_LED_REVERSE_ROWS 0
#define SCB_LED_REVERSE_COLUMNS 0
#define SCB_INVERT_X_DIR 0
#define SCB_INVERT_Y_DIR 0

#define SCB_SCAN_SETTLE_US 1000U
#define SCB_SCAN_FRAME_US 10000U /* 100 Hz nominal, complete 64-square frames. */
#define SCB_SCAN_LIMIT_US 20000U
#define SCB_CONTROL_TICK_MS 1U
#define SCB_DEBOUNCE_SCANS 2U
#define SCB_FEEDBACK_LIMIT_US 100000U
#define SCB_LED_CHANNEL_LIMIT 32U
#define SCB_LINK_TIMEOUT_US 2000000LL
#define SCB_MAGNET_MAX_US 5000000LL
#define SCB_MOVE_TIMEOUT_US 30000000LL
#define SCB_STEP_INTERVAL_US 10000U
#define SCB_STEP_HIGH_US 5U
#define SCB_MAGNET_SETTLE_US 100000U
#define SCB_MAX_STEPS_PER_TILE 2000U
#define SCB_MAX_JOG_STEPS 1000

#endif
