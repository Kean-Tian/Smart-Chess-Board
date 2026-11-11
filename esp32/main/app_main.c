#include "board_pins.h"
#include "scb_core.h"
#include "driver/gpio.h"
#include "driver/rmt_tx.h"
#include "driver/rmt_encoder.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "soc/soc_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include <string.h>

#if !CONFIG_IDF_TARGET_ESP32S2
#error "This firmware targets ESP32-S2-Saola-1 (esp32s2)."
#endif
_Static_assert(SOC_CPU_CORES_NUM == 1, "ESP32-S2 uses one CPU core");
_Static_assert(SCB_PIN_UART_TX == 43 && SCB_PIN_UART_RX == 44, "Keep Saola USB-UART pins reserved");
#define SCB_CHECK_OUTPUT(pin) _Static_assert(GPIO_IS_VALID_OUTPUT_GPIO(pin), "Invalid S2 output GPIO: " #pin)
SCB_CHECK_OUTPUT(SCB_PIN_LED);
SCB_CHECK_OUTPUT(SCB_PIN_ROW_A0);
SCB_CHECK_OUTPUT(SCB_PIN_ROW_A1);
SCB_CHECK_OUTPUT(SCB_PIN_ROW_A2);
SCB_CHECK_OUTPUT(SCB_PIN_MAGNET);
SCB_CHECK_OUTPUT(SCB_PIN_MOTOR_EN);
SCB_CHECK_OUTPUT(SCB_PIN_X_STEP);
SCB_CHECK_OUTPUT(SCB_PIN_X_DIR);
SCB_CHECK_OUTPUT(SCB_PIN_Y_STEP);
SCB_CHECK_OUTPUT(SCB_PIN_Y_DIR);
#undef SCB_CHECK_OUTPUT

static ScbCore core;
static QueueHandle_t tx_queue;
static QueueHandle_t led_queue;
static portMUX_TYPE stats_lock = portMUX_INITIALIZER_UNLOCKED;
static ScbPlatformStats platform_stats;
typedef struct {
    ScbLedGrid grid;
    int64_t queued_at;
} LedFrame;
static rmt_channel_handle_t led_channel;
static rmt_encoder_handle_t led_encoder;
static rmt_symbol_word_t symbols[SCB_LED_COUNT * 24U + 1U];

static bool write_pin(void *ctx, unsigned pin, bool high) {
    (void)ctx;
    return gpio_set_level((gpio_num_t)pin, high) == ESP_OK;
}
/* Read one sensor input; the core chooses which MUX row is active. */
static bool read_pin(void *ctx, unsigned pin) {
    (void)ctx;
    return gpio_get_level((gpio_num_t)pin) != 0;
}
/* Send one STEP pulse to the selected motor driver. */
static bool pulse_pin(void *ctx, unsigned pin) {
    (void)ctx;
    /* A4988 DIR setup margin, then independent X_STEP or Y_STEP. */
    esp_rom_delay_us(SCB_STEP_HIGH_US);
    if (gpio_set_level((gpio_num_t)pin, 1) != ESP_OK) return false;
    esp_rom_delay_us(SCB_STEP_HIGH_US);
    return gpio_set_level((gpio_num_t)pin, 0) == ESP_OK;
}
/* Encode the pixel buffer as GRB pulses and transmit it through RMT. */
static bool transmit_leds(const ScbLedGrid *grid) {
    size_t n = 0;
    for (unsigned i = 0; i < SCB_LED_COUNT; ++i) {
        const uint8_t bytes[] = {grid->pixels[i].green, grid->pixels[i].red, grid->pixels[i].blue};
        for (unsigned ch = 0; ch < 3; ++ch) {
            for (int bit = 7; bit >= 0; --bit) {
                bool one = (bytes[ch] & (1U << bit)) != 0;
                symbols[n++] = (rmt_symbol_word_t){
                    .level0 = 1, .duration0 = one ? 9 : 3,
                    .level1 = 0, .duration1 = one ? 3 : 9,
                };
            }
        }
    }
    /* 10 MHz ticks: at least 300 us LOW reset at the end of every frame. */
    symbols[n++] = (rmt_symbol_word_t){.level0 = 0, .duration0 = 1500,
                                           .level1 = 0, .duration1 = 1500};
    const rmt_transmit_config_t config = {.loop_count = 0};
    if (rmt_transmit(led_channel, led_encoder, symbols, n * sizeof(symbols[0]), &config) != ESP_OK)
        return false;
    return rmt_tx_wait_all_done(led_channel, 20) == ESP_OK;
}
/* Queue the latest LED state without blocking sensor scanning. */
static bool show_leds(void *ctx, const ScbLedGrid *grid) {
    (void)ctx;
    LedFrame frame = {.grid = *grid, .queued_at = esp_timer_get_time()};
    /* Copy the pixels: the control task may immediately update its own grid. */
    return xQueueOverwrite(led_queue, &frame) == pdTRUE;
}
/* Read LED completion statistics and available internal heap. */
static bool read_stats(void *ctx, ScbPlatformStats *out) {
    (void)ctx;
    portENTER_CRITICAL(&stats_lock);
    *out = platform_stats;
    portEXIT_CRITICAL(&stats_lock);
    out->heap_free = heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    out->heap_min = heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    return true;
}
/* Run queued LED transfers and record completion time or failure. */
static void led_writer(void *unused) {
    (void)unused;
    LedFrame frame;
    for (;;) {
        if (xQueueReceive(led_queue, &frame, portMAX_DELAY) != pdTRUE) continue;
        bool ok = transmit_leds(&frame.grid);
        unsigned elapsed = (unsigned)(esp_timer_get_time() - frame.queued_at);
        portENTER_CRITICAL(&stats_lock);
        platform_stats.led_last_us = elapsed;
        if (elapsed > platform_stats.led_max_us) platform_stats.led_max_us = elapsed;
        if (elapsed >= SCB_FEEDBACK_LIMIT_US) ++platform_stats.led_late;
        if (!ok) ++platform_stats.led_failed;
        portEXIT_CRITICAL(&stats_lock);
        if (!ok) {
            /* Quiesce the channel before reusing the in-flight symbol buffer. */
            ESP_ERROR_CHECK(rmt_disable(led_channel));
            ESP_ERROR_CHECK(rmt_enable(led_channel));
        }
    }
}
/* Queue one complete protocol line for the UART worker. */
static void emit_frame(void *ctx, const char *line) {
    (void)ctx;
    char frame[SCB_LINE_CAPACITY] = {0};
    size_t n = strlen(line);
    if (n >= sizeof(frame)) return;
    memcpy(frame, line, n);
    /* Dropping a complete frame under backpressure never splices two lines. */
    (void)xQueueSend(tx_queue, frame, 0);
}
/* Send queued reply/event lines through the onboard USB-UART bridge. */
static void serial_writer(void *unused) {
    (void)unused;
    char frame[SCB_LINE_CAPACITY];
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
/* Set sensor pins as inputs and control pins as outputs; start actuators off. */
static void configure_gpio(void) {
    const unsigned outs[] = {SCB_PIN_ROW_A0, SCB_PIN_ROW_A1, SCB_PIN_ROW_A2,
        SCB_PIN_X_STEP, SCB_PIN_X_DIR, SCB_PIN_Y_STEP, SCB_PIN_Y_DIR,
        SCB_PIN_MOTOR_EN, SCB_PIN_MAGNET};
    uint64_t output_mask = 0, input_mask = 0;
    for (unsigned i = 0; i < sizeof(outs) / sizeof(outs[0]); ++i) {
        output_mask |= UINT64_C(1) << outs[i];
        ESP_ERROR_CHECK(gpio_set_level((gpio_num_t)outs[i], outs[i] == SCB_PIN_MOTOR_EN));
    }
    const unsigned inputs[] = SCB_COLUMN_PINS;
    for (unsigned i = 0; i < 8; ++i) input_mask |= UINT64_C(1) << inputs[i];
    const gpio_config_t out_config = {.pin_bit_mask = output_mask, .mode = GPIO_MODE_OUTPUT};
    configASSERT((input_mask & output_mask) == 0);
    configASSERT((input_mask & ((1ULL << SCB_PIN_LED) |
        (1ULL << SCB_PIN_UART_TX) | (1ULL << SCB_PIN_UART_RX))) == 0);
    const gpio_config_t in_config = {
        .pin_bit_mask = input_mask,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&out_config));
    /* GPIO1-8 only observe the sensor PCB's externally pulled-up outputs.
     * HIGH is a measured input, not a request for this MCU to drive HIGH.
     */
    ESP_ERROR_CHECK(gpio_config(&in_config));
}
/* Every 1 ms, advance the core and pass incoming UART bytes to its parser. */
static void control_task(void *unused) {
    (void)unused;
    TickType_t wake = xTaskGetTickCount();
    unsigned led_failures = 0;
    for (;;) {
        uint8_t buf[64];
        portENTER_CRITICAL(&stats_lock);
        unsigned failures = platform_stats.led_failed;
        portEXIT_CRITICAL(&stats_lock);
        if (failures != led_failures) {
            led_failures = failures;
            /* Only this task owns ScbCore and controls motor shutdown. */
            scb_core_fault(&core, "LED_OUTPUT");
        }
        scb_core_tick(&core, esp_timer_get_time());
        int n = uart_read_bytes(UART_NUM_0, buf, sizeof(buf), 0);
        if (n > 0) scb_core_feed(&core, buf, (size_t)n, esp_timer_get_time());
        /* Absolute scheduling avoids adding work time to every 1 ms delay. */
        xTaskDelayUntil(&wake, pdMS_TO_TICKS(SCB_CONTROL_TICK_MS));
    }
}
/* Firmware entry: initialize GPIO, UART, RMT, core state and worker tasks. */
void app_main(void) {
    configure_gpio();
    esp_log_level_set("*", ESP_LOG_NONE); /* Do not mix logs into the application protocol. */
    const uart_config_t uart = {.baud_rate = SCB_UART_BAUD,
        .data_bits = UART_DATA_8_BITS, .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1, .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT};
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_0, &uart));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM_0, SCB_PIN_UART_TX, SCB_PIN_UART_RX,
                                UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0, 2048, 2048, 0, NULL, 0));
    tx_queue = xQueueCreate(32, SCB_LINE_CAPACITY);
    led_queue = xQueueCreate(1, sizeof(LedFrame));
    configASSERT(tx_queue && led_queue);
    configASSERT(xTaskCreate(serial_writer, "scb_serial_tx", 3072, NULL, 4, NULL) == pdPASS);
    const rmt_tx_channel_config_t rmt = {.gpio_num = SCB_PIN_LED,
        .clk_src = RMT_CLK_SRC_DEFAULT, .resolution_hz = 10000000,
        .mem_block_symbols = 2 * SOC_RMT_MEM_WORDS_PER_CHANNEL,
        .trans_queue_depth = 1, .flags.with_dma = false};
    ESP_ERROR_CHECK(rmt_new_tx_channel(&rmt, &led_channel));
    const rmt_copy_encoder_config_t encoder = {};
    ESP_ERROR_CHECK(rmt_new_copy_encoder(&encoder, &led_encoder));
    ESP_ERROR_CHECK(rmt_enable(led_channel));
    configASSERT(xTaskCreate(led_writer, "scb_led", 3072, NULL, 3, NULL) == pdPASS);
    ScbIo io = {.write = write_pin, .read = read_pin, .pulse = pulse_pin,
        .show_leds = show_leds, .emit = emit_frame, .stats = read_stats};
    if (!scb_core_init(&core, io, esp_timer_get_time())) {
        scb_core_fault(&core, "INIT");
        for (;;) vTaskDelay(pdMS_TO_TICKS(1000));
    }
    /* One S2 CPU: priority 10 control preempts the blocking serial/LED workers. */
    configASSERT(xTaskCreate(control_task, "scb_control", 8192, NULL, 10, NULL) == pdPASS);
}
