#ifndef SCB_MCU_CONTROLLER_H
#define SCB_MCU_CONTROLLER_H

#include <stdbool.h>
#include <stdint.h>

#define SCB_BOARD_SQUARE_COUNT 64
#define SCB_INPUT_DEBOUNCE_MS 25u

typedef struct {
    void *context;
    bool (*button_pressed)(void *context);
    bool (*read_hall_sensor)(void *context, uint8_t square);
    void (*write_status_led)(void *context, bool on);
    void (*send_uart_line)(void *context, const char *line);
} ScbPlatform;

typedef struct {
    bool stable;
    bool candidate;
    bool initialized;
    uint32_t changed_at;
} ScbDebouncedInput;

typedef struct {
    ScbPlatform platform;
    bool button_test_mode;
    bool button_initialized;
    bool button_stable;
    bool button_candidate;
    bool test_move_pending;
    uint32_t button_changed_at;
    uint8_t test_square;
    int pending_from;
    ScbDebouncedInput sensors[SCB_BOARD_SQUARE_COUNT];
    bool test_sensors[SCB_BOARD_SQUARE_COUNT];
} ScbMcuController;

void scb_mcu_init(ScbMcuController *controller, ScbPlatform platform, bool button_test_mode);
void scb_mcu_loop(ScbMcuController *controller, uint32_t now_ms);
bool scb_mcu_sensor_occupied(const ScbMcuController *controller, uint8_t square);

#endif
