#ifndef SCB_BOARD_PINS_H
#define SCB_BOARD_PINS_H
#ifdef ESP_PLATFORM
#include "sdkconfig.h"
#endif

/* SCBMasterPCBV3 + SCBSensorPCBV2.2, KiCad schematic AND PCB checked 2026-11-24.
 * GPIO numbers are not QFN pad numbers. Default IDC16 cable: pin n -> pin n.
 */
#define SCB_PIN_LED 21 /* LED_IN_3V3 -> U5 level shifter -> J4.9 */
#define SCB_MASTER_MUX_IN1 8
#define SCB_MASTER_MUX_IN2 9
#define SCB_MASTER_MUX_IN3 10
#if defined(CONFIG_SCB_SENSOR_NAMED_WIRING) && CONFIG_SCB_SENSOR_NAMED_WIRING
/* Custom cable crossed by signal NAME; not the default straight cable. */
#define SCB_PIN_ROW_A0 8
#define SCB_PIN_ROW_A1 9
#define SCB_PIN_ROW_A2 10
#else
#define SCB_PIN_ROW_A0 10 /* sensor J1.11 <- master J4.11 MUX_IN3 */
#define SCB_PIN_ROW_A1 9
#define SCB_PIN_ROW_A2 8 /* sensor J1.15 <- master J4.15 MUX_IN1 */
#endif
/* Sensor DIG_OUT1..8, also matching V3 master signal names. */
#define SCB_COLUMN_PINS {13, 14, 4, 5, 11, 12, 6, 7}
#define SCB_PIN_MAGNET 33
/* V3 schematic and PCB agree; obsolete V2 STEP/DIR selection removed. */
#define SCB_PIN_X_STEP 35
#define SCB_PIN_X_DIR 34
#define SCB_PIN_Y_STEP 37
#define SCB_PIN_Y_DIR 36
#define SCB_PIN_MOTOR_EN 38 /* active LOW */
#define SCB_PIN_UART_TX 17 /* J6.1, application UART1, NOT ROM UART0 */
#define SCB_PIN_UART_RX 18 /* J6.2 */
#define SCB_PIN_USB_DM 19
#define SCB_PIN_USB_DP 20
#define SCB_PIN_PCB_TEST 46 /* D6 anode, QFN pad 52; HIGH after app startup. */
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
