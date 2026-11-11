#ifndef SCB_BOARD_PINS_H
#define SCB_BOARD_PINS_H

#define SCB_PIN_LED 17
/* MUX_IN1/2/3 (A0/A1/A2), least-significant address bit first.
 * All three outputs switch automatically during full-board scanning.
 */
#define SCB_PIN_ROW_A0 36
#define SCB_PIN_ROW_A1 37
#define SCB_PIN_ROW_A2 38
#define SCB_COLUMN_PINS {1, 2, 3, 4, 5, 6, 7, 8}
#define SCB_PIN_MAGNET 12
#define SCB_PIN_X_STEP 14
#define SCB_PIN_X_DIR 21
#define SCB_PIN_Y_STEP 15
#define SCB_PIN_Y_DIR 16
#define SCB_PIN_MOTOR_EN 13
#define SCB_PIN_UART_TX 43
#define SCB_PIN_UART_RX 44
#define SCB_UART_BAUD 115200
#define SCB_GPIO_COUNT 47U


#define SCB_SENSOR_REVERSE_ROWS 0
#define SCB_SENSOR_REVERSE_COLUMNS 0
/* Verified on this sensor board: placing a magnet drives DIG_OUT HIGH. */
#define SCB_SENSOR_ACTIVE_LOW 0
#define SCB_LED_REVERSE_ROWS 0
#define SCB_LED_REVERSE_COLUMNS 0
#define SCB_INVERT_X_DIR 0
#define SCB_INVERT_Y_DIR 0

#define SCB_SCAN_SETTLE_US 1000U
#define SCB_SCAN_FRAME_US 10000U /* 100 Hz nominal, complete 64-square frames. */
#define SCB_SCAN_LIMIT_US 20000U
#define SCB_CONTROL_TICK_MS 1U
#define SCB_DEBOUNCE_SCANS 2U
/* Coalesce automatic sensor traces to at most 5 snapshots/second. SCAN forces one. */
#define SCB_SENSOR_TRACE_INTERVAL_US 200000LL
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
