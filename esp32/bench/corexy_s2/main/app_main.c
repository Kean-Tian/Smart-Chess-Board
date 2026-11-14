#include "bench_pins.h"
#include "motor_bench.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include <string.h>

#if !CONFIG_IDF_TARGET_ESP32S2
#error "This test harness is for ESP32-S2-Saola-1, not the final S3 PCB."
#endif
#define CHECK_OUTPUT(pin) _Static_assert(GPIO_IS_VALID_OUTPUT_GPIO(pin), "Invalid S2 GPIO: " #pin)
CHECK_OUTPUT(SCB_BENCH_A_STEP);
CHECK_OUTPUT(SCB_BENCH_A_DIR);
CHECK_OUTPUT(SCB_BENCH_B_STEP);
CHECK_OUTPUT(SCB_BENCH_B_DIR);
CHECK_OUTPUT(SCB_BENCH_ENABLE);
CHECK_OUTPUT(SCB_BENCH_EM_CTRL);
#undef CHECK_OUTPUT
static ScbMotorBench bench;
static QueueHandle_t tx_queue;
static bool write_pin(void *ctx, unsigned pin, bool high) {
    (void)ctx; return gpio_set_level((gpio_num_t)pin, high) == ESP_OK;
}
static void output(void *ctx, const char *line) {
    (void)ctx;
    char frame[SCB_BENCH_LINE_CAPACITY] = {0};
    size_t length = strlen(line);
    if (length >= sizeof(frame)) return;
    memcpy(frame, line, length);
    (void)xQueueSend(tx_queue, frame, 0);
}
static void serial_writer(void *ctx) {
    (void)ctx; char frame[SCB_BENCH_LINE_CAPACITY];
    for (;;) {
        if (xQueueReceive(tx_queue, frame, portMAX_DELAY) != pdTRUE) continue;
        size_t sent = 0, length = strlen(frame);
        while (sent < length) {
            int n = uart_write_bytes(UART_NUM_0, frame + sent, length - sent);
            if (n > 0) sent += (size_t)n;
            else vTaskDelay(pdMS_TO_TICKS(5));
        }
    }
}
void app_main(void) {
    const unsigned pins[] = {SCB_BENCH_ENABLE, SCB_BENCH_A_STEP, SCB_BENCH_B_STEP,
        SCB_BENCH_A_DIR, SCB_BENCH_B_DIR, SCB_BENCH_EM_CTRL};
    uint64_t mask = 0;
    /* Preload safe levels before changing output modes. Magnet stays OFF.
     * This test never initializes sensors/LEDs and never energizes EM_CTRL.
     */
    for (unsigned i = 0; i < sizeof(pins) / sizeof(pins[0]); ++i) {
        ESP_ERROR_CHECK(gpio_set_level((gpio_num_t)pins[i], pins[i] == SCB_BENCH_ENABLE));
        mask |= UINT64_C(1) << pins[i];
    }
    const gpio_config_t gpio = {.pin_bit_mask = mask, .mode = GPIO_MODE_OUTPUT};
    ESP_ERROR_CHECK(gpio_config(&gpio));
    esp_log_level_set("*", ESP_LOG_NONE);
    const uart_config_t uart = {.baud_rate = 115200, .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE, .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE, .source_clk = UART_SCLK_DEFAULT};
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_0, &uart));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM_0, SCB_BENCH_UART_TX, SCB_BENCH_UART_RX,
                                UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0, 2048, 2048, 0, NULL, 0));
    tx_queue = xQueueCreate(32, SCB_BENCH_LINE_CAPACITY); configASSERT(tx_queue);
    configASSERT(xTaskCreate(serial_writer, "motor_bench_tx", 3072, NULL, 4, NULL) == pdPASS);
    const ScbMotorPins motor_pins = {.step = {SCB_BENCH_A_STEP, SCB_BENCH_B_STEP},
        .dir = {SCB_BENCH_A_DIR, SCB_BENCH_B_DIR}, .enable = SCB_BENCH_ENABLE};
    scb_motor_bench_init(&bench, (ScbMotorIo){.write = write_pin}, motor_pins, output, NULL);
    vTaskPrioritySet(NULL, 10);
    TickType_t wake = xTaskGetTickCount();
    for (;;) {
        scb_motor_bench_tick(&bench, esp_timer_get_time());
        uint8_t bytes[64]; int n = uart_read_bytes(UART_NUM_0, bytes, sizeof(bytes), 0);
        if (n > 0) scb_motor_bench_feed(&bench, bytes, (size_t)n, esp_timer_get_time());
        xTaskDelayUntil(&wake, pdMS_TO_TICKS(1));
    }
}
