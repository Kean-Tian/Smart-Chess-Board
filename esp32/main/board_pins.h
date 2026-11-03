#ifndef SCB_BOARD_PINS_H
#define SCB_BOARD_PINS_H

/* WeMos LOLIN32 V1.0.0, classic ESP-WROOM-32 / ESP32, 4 MB Flash, no PSRAM.
 * Native GPIO numbers, NOT chip/module-pad numbers from the pinout diagram.
 * Test harness mapping: docs/PCB_Connection_Map.md.
 */
#define SCB_PIN_LED 4
#define SCB_PIN_ROW_A0 16
#define SCB_PIN_ROW_A1 17
#define SCB_PIN_ROW_A2 18
#define SCB_COLUMN_PINS {36, 39, 34, 35, 32, 33, 25, 26}
#define SCB_PIN_MAGNET 27
#define SCB_PIN_X_STEP 19
#define SCB_PIN_X_DIR 21
#define SCB_PIN_Y_STEP 22
#define SCB_PIN_Y_DIR 23
#define SCB_PIN_MOTOR_EN 13 /* Shared active-low enable; external 10k pull-up to 3.3 V. */
#define SCB_PIN_UART_TX 1   /* Onboard CP2104 bridge RX. Reserve for communication. */
#define SCB_PIN_UART_RX 3   /* Onboard CP2104 bridge TX. Reserve for communication. */
#define SCB_UART_BAUD 115200
#define SCB_GPIO_COUNT 40U

/* GPIO34/35/36/39 are INPUT ONLY, with no internal pull resistors.
 * Sensor comparator outputs require external 3.3 V pull-ups.
 * GPIO6-11 belong to Flash. Avoid boot straps 0/2/5/12/15.
 * The onboard active-low LED on GPIO5 is intentionally not assigned.
 * GPIO16/17 are available on this WROOM board, not a WROVER/PSRAM substitute.
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
