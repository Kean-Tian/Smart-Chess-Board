#include "../include/scb/mcu_controller.h"

#include <stdio.h>
#include <string.h>

static void square_name(uint8_t square, char name[3]) {
    name[0] = (char)('a' + square % 8);
    name[1] = (char)('1' + square / 8);
    name[2] = '\0';
}

void scb_mcu_init(ScbMcuController *controller, ScbPlatform platform, bool button_test_mode) {
    if (controller == NULL) return;
    memset(controller, 0, sizeof(*controller));
    controller->platform = platform;
    controller->button_test_mode = button_test_mode;
    controller->pending_from = -1;
    if (button_test_mode) {
        controller->test_square = 12; /* e2 is occupied in the standard starting position. */
        controller->test_sensors[controller->test_square] = true;
    }
}

bool scb_mcu_sensor_occupied(const ScbMcuController *controller, uint8_t square) {
    return controller != NULL && square < SCB_BOARD_SQUARE_COUNT &&
           controller->sensors[square].initialized && controller->sensors[square].stable;
}

static void update_button(ScbMcuController *controller, uint32_t now_ms) {
    bool raw_pressed;
    if (!controller->button_test_mode || controller->platform.button_pressed == NULL) return;
    raw_pressed = controller->platform.button_pressed(controller->platform.context);
    if (!controller->button_initialized) {
        controller->button_initialized = true;
        controller->button_candidate = raw_pressed;
        controller->button_changed_at = now_ms;
        return;
    }
    if (raw_pressed != controller->button_candidate) {
        controller->button_candidate = raw_pressed;
        controller->button_changed_at = now_ms;
    }
    if ((uint32_t)(now_ms - controller->button_changed_at) < SCB_INPUT_DEBOUNCE_MS ||
        controller->button_stable == controller->button_candidate) return;

    controller->button_stable = controller->button_candidate;
    if (controller->button_stable) {
        if (!controller->test_move_pending) {
            controller->test_sensors[controller->test_square] = false;
            controller->test_move_pending = true;
        } else {
            uint8_t destination = (uint8_t)((controller->test_square + 8) % SCB_BOARD_SQUARE_COUNT);
            controller->test_sensors[destination] = true;
            controller->test_square = destination;
            controller->test_move_pending = false;
        }
    }
}

static bool raw_sensor(const ScbMcuController *controller, uint8_t square) {
    if (controller->button_test_mode) return controller->test_sensors[square];
    return controller->platform.read_hall_sensor != NULL &&
           controller->platform.read_hall_sensor(controller->platform.context, square);
}

static void send_sensor_event(ScbMcuController *controller, uint8_t square, bool occupied) {
    char name[3];
    char line[32];
    if (controller->platform.send_uart_line == NULL) return;
    square_name(square, name);
    (void)snprintf(line, sizeof(line), "SCB1 SENSOR %s %u", name, occupied ? 1u : 0u);
    controller->platform.send_uart_line(controller->platform.context, line);
}

static void send_move_event(ScbMcuController *controller, int from, uint8_t to) {
    char from_name[3];
    char to_name[3];
    char line[32];
    if (controller->platform.send_uart_line == NULL || from < 0 || from >= SCB_BOARD_SQUARE_COUNT) return;
    square_name((uint8_t)from, from_name);
    square_name(to, to_name);
    (void)snprintf(line, sizeof(line), "SCB1 MOVE %s %s", from_name, to_name);
    controller->platform.send_uart_line(controller->platform.context, line);
}

static void on_sensor_changed(ScbMcuController *controller, uint8_t square, bool occupied) {
    send_sensor_event(controller, square, occupied);
    if (occupied) {
        if (controller->pending_from >= 0 && controller->pending_from != square) {
            send_move_event(controller, controller->pending_from, square);
            controller->pending_from = -1;
            if (controller->platform.write_status_led != NULL)
                controller->platform.write_status_led(controller->platform.context, false);
        }
    } else {
        controller->pending_from = square;
        if (controller->platform.write_status_led != NULL)
            controller->platform.write_status_led(controller->platform.context, true);
    }
}

static void scan_sensors(ScbMcuController *controller, uint32_t now_ms) {
    for (uint8_t square = 0; square < SCB_BOARD_SQUARE_COUNT; ++square) {
        bool raw = raw_sensor(controller, square);
        ScbDebouncedInput *input = &controller->sensors[square];
        if (raw != input->candidate) {
            input->candidate = raw;
            input->changed_at = now_ms;
        }
        if ((uint32_t)(now_ms - input->changed_at) < SCB_INPUT_DEBOUNCE_MS) continue;
        if (!input->initialized) {
            input->stable = input->candidate;
            input->initialized = true;
        } else if (input->stable != input->candidate) {
            input->stable = input->candidate;
            on_sensor_changed(controller, square, input->stable);
        }
    }
}

void scb_mcu_loop(ScbMcuController *controller, uint32_t now_ms) {
    if (controller == NULL) return;
    update_button(controller, now_ms);
    scan_sensors(controller, now_ms);
}
