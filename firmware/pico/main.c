#include "../include/scb/mcu_controller.h"

#include "hardware/gpio.h"
#include "hardware/uart.h"
#include "pico/stdlib.h"

#include <stdio.h>

static uart_inst_t *const board_uart = uart0;
static const uint32_t uart_baud_rate = 115200;
static const uint button_pin = 2;
static const uint tx_pin = PICO_DEFAULT_UART_TX_PIN;
static const uint rx_pin = PICO_DEFAULT_UART_RX_PIN;
static const uint led_pin = PICO_DEFAULT_LED_PIN;

static bool button_pressed(void *context) {
    (void)context;
    return !gpio_get(button_pin);
}

static bool read_hall_sensor(void *context, uint8_t square) {
    (void)context;
    (void)square;
    return false;
}

static void write_status_led(void *context, bool on) {
    (void)context;
    gpio_put(led_pin, on);
}

static void send_uart_line(void *context, const char *line) {
    (void)context;
    uart_puts(board_uart, line);
    uart_puts(board_uart, "\r\n");
}

int main(void) {
    ScbPlatform platform;
    ScbMcuController controller;
    uart_init(board_uart, uart_baud_rate);
    gpio_set_function(tx_pin, GPIO_FUNC_UART);
    gpio_set_function(rx_pin, GPIO_FUNC_UART);
    uart_set_format(board_uart, 8, 1, UART_PARITY_NONE);
    uart_set_fifo_enabled(board_uart, true);

    gpio_init(button_pin);
    gpio_set_dir(button_pin, GPIO_IN);
    gpio_pull_up(button_pin);
    gpio_init(led_pin);
    gpio_set_dir(led_pin, GPIO_OUT);
    gpio_put(led_pin, false);

    platform.context = NULL;
    platform.button_pressed = button_pressed;
    platform.read_hall_sensor = read_hall_sensor;
    platform.write_status_led = write_status_led;
    platform.send_uart_line = send_uart_line;
    scb_mcu_init(&controller, platform, true);
    send_uart_line(NULL, "SCB1 READY PICO2 BUTTON_TEST");
    while (true) {
        scb_mcu_loop(&controller, to_ms_since_boot(get_absolute_time()));
        tight_loop_contents();
    }
}