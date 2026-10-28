#ifndef SCB_BOARD_PINS_H
#define SCB_BOARD_PINS_H

/* GPIO numbers, NOT physical package pin numbers. Source: supplied master PCB. */
#define SCB_PIN_LED 2
#define SCB_PIN_ROW_A0 4
#define SCB_PIN_ROW_A1 5
#define SCB_PIN_ROW_A2 6
#define SCB_COLUMN_PINS {7, 8, 9, 10, 11, 12, 13, 14}
#define SCB_PIN_MAGNET 33
#define SCB_PIN_X_STEP 34
#define SCB_PIN_X_DIR 35
#define SCB_PIN_Y_STEP 36
#define SCB_PIN_Y_DIR 37
#define SCB_PIN_MOTOR_EN 38 /* Shared A4988 enable, LOW = enabled. */
#define SCB_PIN_USB_DM 19
#define SCB_PIN_USB_DP 20

/* Physical orientation must be checked at a1/h1/a8/h8 before gameplay. */
#define SCB_SENSOR_REVERSE_ROWS 0
#define SCB_SENSOR_REVERSE_COLUMNS 0
#define SCB_LED_REVERSE_ROWS 0
#define SCB_LED_REVERSE_COLUMNS 0
#define SCB_INVERT_X_DIR 0
#define SCB_INVERT_Y_DIR 0

/* This bare-chip PCB uses external W25Q128 quad flash. No octal PSRAM! */
#define SCB_SCAN_SETTLE_US 1000U
#define SCB_DEBOUNCE_SCANS 3U
#define SCB_LINK_TIMEOUT_US 2000000LL
#define SCB_MAGNET_MAX_US 5000000LL
#define SCB_MOVE_TIMEOUT_US 30000000LL
#define SCB_STEP_INTERVAL_US 10000U
#define SCB_STEP_HIGH_US 5U
#define SCB_MAGNET_SETTLE_US 100000U
#define SCB_MAX_STEPS_PER_TILE 2000U
#define SCB_MAX_JOG_STEPS 1000

#endif
