#include "board_pins.h"
#include "driver/gpio.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#if !CONFIG_IDF_TARGET_ESP32S3
#error "This bench firmware is for SCB Master PCB V2 ESP32-S3 only."
#endif

/* Fixed MUX address 000 after application startup on GPIO6/5/4. No scanning
 * or SCB UART tasks run. The PCB native USB uses GPIO19/20.
 * ROM boot/reset pin states are not controlled by this application.
 */
void app_main(void)
{
    const unsigned outputs[] = {SCB_PIN_MOTOR_EN, SCB_PIN_MAGNET,
        SCB_PIN_X_STEP, SCB_PIN_Y_STEP,
        SCB_PIN_ROW_A0, SCB_PIN_ROW_A1, SCB_PIN_ROW_A2};
    uint64_t mask = 0;
    for (unsigned i = 0; i < sizeof(outputs) / sizeof(outputs[0]); ++i) {
        ESP_ERROR_CHECK(gpio_set_level((gpio_num_t)outputs[i],
                                      outputs[i] == SCB_PIN_MOTOR_EN));
        mask |= 1ULL << outputs[i];
    }
    const gpio_config_t config = {
        .pin_bit_mask = mask,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&config));
    const unsigned columns[] = SCB_COLUMN_PINS;
    mask = 0;
    for (unsigned i = 0; i < sizeof(columns) / sizeof(columns[0]); ++i)
        mask |= 1ULL << columns[i];
    const gpio_config_t inputs = {
        .pin_bit_mask = mask,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&inputs));
    for (;;) vTaskDelay(pdMS_TO_TICKS(1000));
}
