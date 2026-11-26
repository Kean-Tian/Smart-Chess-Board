#include "driver/gpio.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#if !CONFIG_IDF_TARGET_ESP32S3
#error "GPIO46 test targets ESP32-S3 only"
#endif
/* Master V3: GPIO46 -> D6 anode -> R17 (680 ohm) -> GND.
 * Only GPIO46 is configured. No scanning, protocol, motors or magnet tasks.
 * HIGH applies after application startup, not during reset/download mode.
 */
void app_main(void) {
    _Static_assert(GPIO_IS_VALID_OUTPUT_GPIO(46), "GPIO46 must support output");
    const gpio_config_t config = {
        .pin_bit_mask = 1ULL << 46,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_set_level(GPIO_NUM_46, 1));
    ESP_ERROR_CHECK(gpio_config(&config));
    for (;;) vTaskDelay(pdMS_TO_TICKS(1000));
}
