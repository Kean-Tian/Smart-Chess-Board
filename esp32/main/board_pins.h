#ifndef SCB_BOARD_PINS_H
#define SCB_BOARD_PINS_H

/* Load wiring selections before defining pins; host tests supply their own flags. */
#ifdef ESP_PLATFORM
#include "sdkconfig.h"
#elif !defined(CONFIG_SCB_MOTOR_PCB_ROUTING)
/* Portable tests use the same default as the fabricated PCB. */
#define CONFIG_SCB_MOTOR_PCB_ROUTING 1
#endif

/* SCBMasterPCBV2 + SCBSensorPCBV2, exported KiCad netlists 2026-11-23.
 * GPIO numbers below are NOT the bare chip's QFN pad numbers.
 */
#define SCB_PIN_LED 2 /* LED_IN_3V3 -> 74AHCT1G125 -> J4.9 */
#define SCB_MASTER_MUX_IN1 4
#define SCB_MASTER_MUX_IN2 5
#define SCB_MASTER_MUX_IN3 6
/* Default: IDC cable pin n -> pin n. J4/J1 labels are NOT in the same order.
 * The scanner exposes sensor A0/A1/A2 and sensor DIG_OUT1..8, after remapping.
 * Select SCB_SENSOR_NAMED_WIRING only for a verified signal-name crossover.
 */
#if defined(CONFIG_SCB_SENSOR_NAMED_WIRING) && CONFIG_SCB_SENSOR_NAMED_WIRING
#define SCB_PIN_ROW_A0 4
#define SCB_PIN_ROW_A1 5
#define SCB_PIN_ROW_A2 6
#define SCB_COLUMN_PINS {7, 8, 9, 10, 11, 12, 13, 14}
#else
#define SCB_PIN_ROW_A0 6 /* sensor J1.11 <- master J4.11 MUX_IN3 */
#define SCB_PIN_ROW_A1 5
#define SCB_PIN_ROW_A2 4 /* sensor J1.15 <- master J4.15 MUX_IN1 */
#define SCB_COLUMN_PINS {13, 14, 10, 9, 11, 12, 8, 7}
#endif
#define SCB_PIN_MAGNET 33 /* EM_CTRL, active HIGH, Q1 low-side switch */
#if defined(CONFIG_SCB_MOTOR_PCB_ROUTING) && CONFIG_SCB_MOTOR_PCB_ROUTING
/* Default: user confirmed the board was fabricated from this PCB layout. */
#define SCB_PIN_X_STEP 35
#define SCB_PIN_X_DIR 34
#define SCB_PIN_Y_STEP 37
#define SCB_PIN_Y_DIR 36
#else
/* Alternative only: the .kicad_sch assignments disagree with fabricated copper. */
#define SCB_PIN_X_STEP 34
#define SCB_PIN_X_DIR 35
#define SCB_PIN_Y_STEP 36
#define SCB_PIN_Y_DIR 37
#endif
#define SCB_PIN_MOTOR_EN 38 /* Both A4988 enable pins, active LOW */
#define SCB_PIN_UART_TX 18 /* J6.1; application UART1, NOT ROM UART0 */
#define SCB_PIN_UART_RX 17 /* J6.2 */
#define SCB_PIN_USB_DM 19
#define SCB_PIN_USB_DP 20
#define SCB_UART_BAUD 115200
#define SCB_GPIO_COUNT 49U


#define SCB_SENSOR_REVERSE_ROWS 0
#define SCB_SENSOR_REVERSE_COLUMNS 0
/* DRV5053 -> diode column -> LM339 non-inverting input, external pull-up.
 * HIGH occupancy assumes the tested magnet orientation raises the column above
 * the fixed reference. Re-verify on the assembled PCB; do not auto-mask faults.
 */
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
