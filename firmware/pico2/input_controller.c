#include "input_controller.h"

#include <stdio.h>

#define DEBOUNCE_READS 3

// 先用简单的“拿起再放下”判断一步棋，吃子等情况以后再补。
static void report_change(
    scb_input_controller *controller,
    uint8_t square,
    bool occupied,
    scb_uart_writer write_uart
) {
    char message[32];

    if (!occupied) {
        controller->lifted_square = (int8_t)square;
        snprintf(message, sizeof(message), "LIFT %u\n", square);
    } else if (controller->lifted_square >= 0) {
        snprintf(
            message,
            sizeof(message),
            "MOVE %d %u\n",
            controller->lifted_square,
            square
        );
        controller->lifted_square = -1;
    } else {
        snprintf(message, sizeof(message), "PLACE %u\n", square);
    }

    // 这里先通过回调发文字，之后再换成 Pico 2 的 UART 函数。
    if (write_uart != NULL) {
        write_uart(message);
    }
}

void scb_input_init(scb_input_controller *controller, scb_hall_reader read_hall) {
    if (controller == NULL || read_hall == NULL) {
        return;
    }

    controller->lifted_square = -1;

    // 开机时先记住 64 个格子的状态，避免把初始棋子当成新动作。
    for (uint8_t square = 0; square < SCB_SQUARE_COUNT; ++square) {
        bool occupied = read_hall(square);
        controller->stable_state[square] = occupied;
        controller->last_reading[square] = occupied;
        controller->same_read_count[square] = 0;
    }
}

void scb_input_poll(
    scb_input_controller *controller,
    scb_hall_reader read_hall,
    scb_uart_writer write_uart
) {
    if (controller == NULL || read_hall == NULL) {
        return;
    }

    for (uint8_t square = 0; square < SCB_SQUARE_COUNT; ++square) {
        bool reading = read_hall(square);

        // 连续读到三次相同结果后才接受，先过滤掉传感器抖动。
        if (reading == controller->last_reading[square]) {
            if (controller->same_read_count[square] < DEBOUNCE_READS) {
                ++controller->same_read_count[square];
            }
        } else {
            controller->last_reading[square] = reading;
            controller->same_read_count[square] = 1;
        }

        if (controller->same_read_count[square] == DEBOUNCE_READS &&
            reading != controller->stable_state[square]) {
            controller->stable_state[square] = reading;
            report_change(controller, square, reading, write_uart);
        }
    }
}

void scb_input_simulate_move(
    scb_input_controller *controller,
    uint8_t from,
    uint8_t to,
    scb_uart_writer write_uart
) {
    if (controller == NULL || from >= SCB_SQUARE_COUNT || to >= SCB_SQUARE_COUNT) {
        return;
    }

    // 测试按钮以后可以调用这里，不接 Hall sensor 也能先检查事件格式。
    controller->stable_state[from] = false;
    controller->stable_state[to] = true;
    report_change(controller, from, false, write_uart);
    report_change(controller, to, true, write_uart);
}
