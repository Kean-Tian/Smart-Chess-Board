#ifndef SCB_INPUT_CONTROLLER_H
#define SCB_INPUT_CONTROLLER_H

#include <stdbool.h>
#include <stdint.h>

#define SCB_SQUARE_COUNT 64

// 之后接 Pico SDK 时，只要把真正的 GPIO 读取函数传进来就可以。
typedef bool (*scb_hall_reader)(uint8_t square);
typedef void (*scb_uart_writer)(const char *message);

typedef struct {
    bool stable_state[SCB_SQUARE_COUNT];
    bool last_reading[SCB_SQUARE_COUNT];
    uint8_t same_read_count[SCB_SQUARE_COUNT];
    int8_t lifted_square;
} scb_input_controller;

void scb_input_init(scb_input_controller *controller, scb_hall_reader read_hall);
void scb_input_poll(
    scb_input_controller *controller,
    scb_hall_reader read_hall,
    scb_uart_writer write_uart
);
void scb_input_simulate_move(
    scb_input_controller *controller,
    uint8_t from,
    uint8_t to,
    scb_uart_writer write_uart
);

#endif
