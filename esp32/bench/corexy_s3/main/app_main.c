#include "bench_pins.h"
#include "motor_bench.h"
#include "driver/gpio.h"
#include "scb_transport.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include <string.h>

#if !CONFIG_IDF_TARGET_ESP32S3
#error "This test harness is for SCB Master PCB V3 ESP32-S3, not the final S3 PCB."
#endif
#define CHECK_OUTPUT(pin) _Static_assert(GPIO_IS_VALID_OUTPUT_GPIO(pin), "Invalid S3 GPIO: " #pin)
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
            int n = scb_transport_write(frame + sent, length - sent, pdMS_TO_TICKS(20));
            if (n > 0) sent += (size_t)n;
            else { (void)scb_transport_write("\n", 1, 0); break; }
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
    ESP_ERROR_CHECK(scb_transport_init());
    tx_queue = xQueueCreate(32, SCB_BENCH_LINE_CAPACITY); configASSERT(tx_queue);
    configASSERT(xTaskCreate(serial_writer, "motor_bench_tx", 3072, NULL, 4, NULL) == pdPASS);
    const ScbMotorPins motor_pins = {.step = {SCB_BENCH_A_STEP, SCB_BENCH_B_STEP},
        .dir = {SCB_BENCH_A_DIR, SCB_BENCH_B_DIR}, .enable = SCB_BENCH_ENABLE};
    scb_motor_bench_init(&bench, (ScbMotorIo){.write = write_pin}, motor_pins, output, NULL);
    vTaskPrioritySet(NULL, 10);
    TickType_t wake = xTaskGetTickCount();
    for (;;) {
        scb_motor_bench_tick(&bench, esp_timer_get_time());
        uint8_t bytes[64]; int n = scb_transport_read(bytes, sizeof(bytes));
        if (n > 0) scb_motor_bench_feed(&bench, bytes, (size_t)n, esp_timer_get_time());
        xTaskDelayUntil(&wake, pdMS_TO_TICKS(1));
    }
}
