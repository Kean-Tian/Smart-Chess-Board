#include "board_pins.h"
#include "scb_core.h"
#include "driver/gpio.h"
#include "driver/rmt_tx.h"
#include "driver/rmt_encoder.h"
#include "driver/usb_serial_jtag.h"
#include "esp_log.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include <string.h>

#if defined(CONFIG_SPIRAM) || defined(CONFIG_ESPTOOLPY_OCT_FLASH)
#error "This PCB uses GPIO33-37 for motion/magnet: disable octal flash and all PSRAM."
#endif

static ScbCore core;
static QueueHandle_t tx_queue;
static rmt_channel_handle_t led_channel;
static rmt_encoder_handle_t led_encoder;
static rmt_symbol_word_t symbols[SCB_LED_COUNT * 24U + 1U];

static bool write_pin(void *ctx, unsigned pin, bool high) {
    (void)ctx;
    return gpio_set_level((gpio_num_t)pin, high) == ESP_OK;
}
static bool read_pin(void *ctx, unsigned pin) {
    (void)ctx;
    return gpio_get_level((gpio_num_t)pin) != 0;
}
static bool pulse_pin(void *ctx, unsigned pin) {
    (void)ctx;
    /* A4988 DIR setup margin, then independent X_STEP or Y_STEP. */
    esp_rom_delay_us(SCB_STEP_HIGH_US);
    if (gpio_set_level((gpio_num_t)pin, 1) != ESP_OK) return false;
    esp_rom_delay_us(SCB_STEP_HIGH_US);
    return gpio_set_level((gpio_num_t)pin, 0) == ESP_OK;
}
static bool show_leds(void *ctx, const ScbLedGrid *grid) {
    (void)ctx;
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
    return rmt_tx_wait_all_done(led_channel, 100) == ESP_OK;
}
static void emit_frame(void *ctx, const char *line) {
    (void)ctx;
    char frame[SCB_LINE_CAPACITY] = {0};
    size_t n = strlen(line);
    if (n >= sizeof(frame)) return;
    memcpy(frame, line, n);
    /* Dropping a complete frame under backpressure never splices two lines. */
    (void)xQueueSend(tx_queue, frame, 0);
}
static void usb_writer(void *unused) {
    (void)unused;
    char frame[SCB_LINE_CAPACITY];
    for (;;) {
        if (xQueueReceive(tx_queue, frame, portMAX_DELAY) != pdTRUE) continue;
        size_t sent = 0, length = strlen(frame);
        while (sent < length) {
            int n = usb_serial_jtag_write_bytes(frame + sent, length - sent, pdMS_TO_TICKS(5));
            if (n > 0) sent += (size_t)n;
            else vTaskDelay(pdMS_TO_TICKS(5));
        }
    }
}
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
    const gpio_config_t in_config = {.pin_bit_mask = input_mask, .mode = GPIO_MODE_INPUT};
    ESP_ERROR_CHECK(gpio_config(&out_config));
    /* The sensor PCB already has 3.3 V LM339 pull-ups. */
    ESP_ERROR_CHECK(gpio_config(&in_config));
}
void app_main(void) {
    configure_gpio();
    esp_log_level_set("*", ESP_LOG_NONE); /* Do not mix logs into the application protocol. */
    usb_serial_jtag_driver_config_t usb = {.tx_buffer_size = 2048, .rx_buffer_size = 1024};
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&usb));
    tx_queue = xQueueCreate(32, SCB_LINE_CAPACITY);
    configASSERT(tx_queue);
    configASSERT(xTaskCreate(usb_writer, "scb_usb_tx", 3072, NULL, 4, NULL) == pdPASS);
    const rmt_tx_channel_config_t rmt = {.gpio_num = SCB_PIN_LED,
        .clk_src = RMT_CLK_SRC_DEFAULT, .resolution_hz = 10000000,
        .mem_block_symbols = 1024, .trans_queue_depth = 1, .flags.with_dma = true};
    ESP_ERROR_CHECK(rmt_new_tx_channel(&rmt, &led_channel));
    const rmt_copy_encoder_config_t encoder = {};
    ESP_ERROR_CHECK(rmt_new_copy_encoder(&encoder, &led_encoder));
    ESP_ERROR_CHECK(rmt_enable(led_channel));
    ScbIo io = {.write = write_pin, .read = read_pin, .pulse = pulse_pin,
        .show_leds = show_leds, .emit = emit_frame};
    if (!scb_core_init(&core, io, esp_timer_get_time())) {
        scb_core_fault(&core, "INIT");
        for (;;) vTaskDelay(pdMS_TO_TICKS(1000));
    }
    for (;;) {
        uint8_t buf[64];
        int64_t now = esp_timer_get_time();
        scb_core_tick(&core, now);
        int n = usb_serial_jtag_read_bytes(buf, sizeof(buf), 0);
        if (n > 0) scb_core_feed(&core, buf, (size_t)n, esp_timer_get_time());
        /* Scan advances one row per settling interval; motion never blocks it. */
        vTaskDelay(1);
    }
}
