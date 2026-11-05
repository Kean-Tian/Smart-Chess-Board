#include "board_pins.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if !CONFIG_IDF_TARGET_ESP32S2
#error "This test is for ESP32-S2-Saola-1 only."
#endif
_Static_assert(GPIO_IS_VALID_OUTPUT_GPIO(SCB_PIN_ROW_A0), "A0 must support output");
_Static_assert(GPIO_IS_VALID_OUTPUT_GPIO(SCB_PIN_ROW_A1), "A1 must support output");
_Static_assert(GPIO_IS_VALID_OUTPUT_GPIO(SCB_PIN_ROW_A2), "A2 must support output");

/* Standalone fixed-address test using the shared board_pins.h map:
 * A0 HIGH, A1/A2 LOW (GPIO36/37/38 = 100, decoder address 001).
 * No board scanning runs. Flash the main release to restore scanning.
 * ROM/reset states are outside the control of app_main.
 */
static void reply(const char *kind, unsigned id, const char *payload)
{
    char output[192];
    int length = snprintf(output, sizeof(output), "%s %u %s\n", kind, id, payload);
    if (length > 0 && (size_t)length < sizeof(output))
        (void)uart_write_bytes(UART_NUM_0, output, length);
}

static void handle_command(char *line)
{
    unsigned id = 0;
    char *command = line;
    while (*command == ' ' || *command == '\t') ++command;
    if (*command == '@') {
        char *end;
        ++command;
        if (*command < '0' || *command > '9') {
            reply("ERR", 0, "ID");
            return;
        }
        errno = 0;
        unsigned long number = strtoul(command, &end, 10);
        if (errno || number > INT_MAX || (*end != ' ' && *end != '\t')) {
            reply("ERR", 0, "ID");
            return;
        }
        id = (unsigned)number;
        command = end;
    }
    while (*command == ' ' || *command == '\t') ++command;
    size_t length = strlen(command);
    while (length && (command[length - 1] == ' ' || command[length - 1] == '\t'))
        command[--length] = '\0';

    if (!strcmp(command, "PING") || !strcmp(command, "STOP") || !strcmp(command, "DISARM")) {
        /* Actuators stay disabled. STOP does not change the fixed MUX address. */
        reply("ACK", id, command);
    } else if (!strcmp(command, "STATUS")) {
        char status[128];
        snprintf(status, sizeof(status),
                 "armed=0 moving=0 magnet=0 mode=A0_HIGH gpio%u=%d gpio%u=%d gpio%u=%d",
                 SCB_PIN_ROW_A0, gpio_get_level(SCB_PIN_ROW_A0),
                 SCB_PIN_ROW_A1, gpio_get_level(SCB_PIN_ROW_A1),
                 SCB_PIN_ROW_A2, gpio_get_level(SCB_PIN_ROW_A2));
        reply("STATUS", id, status);
    } else if (!strcmp(command, "INPUTS")) {
        const unsigned pins[] = SCB_COLUMN_PINS;
        char inputs[16] = "inputs=";
        for (unsigned i = 0; i < 8; ++i)
            inputs[7 + i] = gpio_get_level((gpio_num_t)pins[i]) ? '1' : '0';
        inputs[15] = '\0';
        reply("STATUS", id, inputs);
    } else if (!strcmp(command, "SCAN") || !strcmp(command, "RAW")) {
        reply("ERR", id, "SCAN_DISABLED_FIXED_A0");
    } else {
        reply("ERR", id, "COMMAND_UNAVAILABLE_IN_A0_TEST");
    }
}

static void uart_console(void)
{
    const uart_config_t config = {
        .baud_rate = SCB_UART_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_0, &config));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM_0, SCB_PIN_UART_TX, SCB_PIN_UART_RX,
                                UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0, 512, 0, 0, NULL, 0));
    const char hello[] = "HELLO SCB_S2_A0_HIGH 1\n";
    (void)uart_write_bytes(UART_NUM_0, hello, sizeof(hello) - 1);
    char line[128];
    size_t used = 0;
    bool discard = false;
    for (;;) {
        unsigned char buffer[64];
        int count = uart_read_bytes(UART_NUM_0, buffer, sizeof(buffer), pdMS_TO_TICKS(20));
        for (int i = 0; i < count; ++i) {
            unsigned char ch = buffer[i];
            if (ch == '\n') {
                if (discard) reply("ERR", 0, "LINE_DROPPED");
                else if (used) {
                    line[used] = '\0';
                    handle_command(line);
                }
                used = 0;
                discard = false;
            } else if (ch != '\r' && !discard) {
                if ((ch < 32 && ch != '\t') || ch > 126 || used == sizeof(line) - 1)
                    discard = true;
                else line[used++] = (char)ch;
            }
        }
    }
}

void app_main(void)
{
    const gpio_num_t idle_pins[] = {SCB_PIN_MOTOR_EN, SCB_PIN_MAGNET,
                                  SCB_PIN_X_STEP, SCB_PIN_Y_STEP};
    uint64_t mask = 0;
    for (unsigned i = 0; i < sizeof(idle_pins) / sizeof(idle_pins[0]); ++i) {
        ESP_ERROR_CHECK(gpio_set_level(idle_pins[i], idle_pins[i] == SCB_PIN_MOTOR_EN));
        mask |= 1ULL << idle_pins[i];
    }
    const gpio_config_t idle = {
        .pin_bit_mask = mask,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&idle));

    const unsigned inputs[] = SCB_COLUMN_PINS;
    mask = 0;
    for (unsigned i = 0; i < sizeof(inputs) / sizeof(inputs[0]); ++i)
        mask |= 1ULL << inputs[i];
    const gpio_config_t columns = {
        .pin_bit_mask = mask,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&columns));
    ESP_ERROR_CHECK(gpio_set_level(SCB_PIN_ROW_A0, 1));
    ESP_ERROR_CHECK(gpio_set_level(SCB_PIN_ROW_A1, 0));
    ESP_ERROR_CHECK(gpio_set_level(SCB_PIN_ROW_A2, 0));
    const gpio_config_t address = {
        .pin_bit_mask = (1ULL << SCB_PIN_ROW_A0) | (1ULL << SCB_PIN_ROW_A1) |
                        (1ULL << SCB_PIN_ROW_A2),
        .mode = GPIO_MODE_INPUT_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&address));
    uart_console();
}
