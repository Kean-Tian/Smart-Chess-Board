/*
 * Smart Chess Board - dual A4988 / NEMA-17 demo (ESP32-S2-Saola-1 prototype)
 *
 * Wiring (see README.md): STEP/DIR/EN from the GPIOs in board_pins.h to both A4988 boards.
 */
#include <stdint.h>
#include <stdlib.h>

#include "driver/gpio.h"
#include "esp_check.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "board_pins.h"
#include "stepper.h"

static const char *TAG = "scb_demo";

/* Set to 2/4/8/16 if you wire MS1-MS3 for microstepping. 1 = full step (MS pins floating). */
#define MICROSTEP       16
#define STEPS_PER_REV   (200 * MICROSTEP)      /* 1.8 deg motor */

/* Conservative defaults. Raise MAX_SPS gradually; if the motor stalls or buzzes, back off. */
#define START_SPS       (50 * MICROSTEP)
#define MAX_SPS         (150 * MICROSTEP)
#define ACCEL_SPS2      (300 * MICROSTEP)

static esp_err_t motor_enable_pin_init(void)
{
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << PIN_MOTOR_EN,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_RETURN_ON_ERROR(gpio_config(&io), TAG, "EN gpio");
    return gpio_set_level(PIN_MOTOR_EN, 1);    /* /ENABLE is active low: start disabled */
}

static void motors_enable(bool on)
{
    gpio_set_level(PIN_MOTOR_EN, on ? 0 : 1);
}

static uint32_t scale_to_share(uint32_t value, uint32_t steps, uint32_t major_steps)
{
    uint32_t v = (uint32_t)(((uint64_t)value * steps) / major_steps);
    return (v == 0u) ? 1u : v;
}

/* Scale one axis' speed profile by its share of the longer axis so both axes finish together. */
static esp_err_t set_scaled_profile(stepper_t *s, uint32_t steps, uint32_t major_steps)
{
    uint32_t v0 = scale_to_share(START_SPS, steps, major_steps);
    uint32_t vmax = scale_to_share(MAX_SPS, steps, major_steps);
    uint32_t accel = scale_to_share(ACCEL_SPS2, steps, major_steps);
    if (vmax < v0) {
        vmax = v0;
    }
    return stepper_set_profile(s, v0, vmax, accel);
}

/* Coordinated relative move: straight line in step space. */
static esp_err_t move_xy(stepper_t *x, stepper_t *y, int32_t dx, int32_t dy)
{
    uint32_t ax = (uint32_t)abs(dx);
    uint32_t ay = (uint32_t)abs(dy);
    if (ax == 0u && ay == 0u) {
        return ESP_OK;
    }
    uint32_t major = (ax > ay) ? ax : ay;

    if (ax != 0u) {
        ESP_RETURN_ON_ERROR(set_scaled_profile(x, ax, major), TAG, "x profile");
    }
    if (ay != 0u) {
        ESP_RETURN_ON_ERROR(set_scaled_profile(y, ay, major), TAG, "y profile");
    }
    ESP_RETURN_ON_ERROR(stepper_move(x, dx), TAG, "x move");
    ESP_RETURN_ON_ERROR(stepper_move(y, dy), TAG, "y move");
    ESP_RETURN_ON_ERROR(stepper_wait_idle(x, portMAX_DELAY), TAG, "x wait");
    ESP_RETURN_ON_ERROR(stepper_wait_idle(y, portMAX_DELAY), TAG, "y wait");
    return ESP_OK;
}

void app_main(void)
{
    ESP_ERROR_CHECK(motor_enable_pin_init());

    stepper_config_t xcfg = {
        .step_pin = PIN_X_STEP,
        .dir_pin = PIN_X_DIR,
        .invert_dir = X_INVERT_DIR,
        .start_speed_sps = START_SPS,
        .max_speed_sps = MAX_SPS,
        .accel_sps2 = ACCEL_SPS2,
    };
    stepper_config_t ycfg = xcfg;
    ycfg.step_pin = PIN_Y_STEP;
    ycfg.dir_pin = PIN_Y_DIR;
    ycfg.invert_dir = Y_INVERT_DIR;

    stepper_t *x = NULL;
    stepper_t *y = NULL;
    ESP_ERROR_CHECK(stepper_new(&xcfg, &x));
    ESP_ERROR_CHECK(stepper_new(&ycfg, &y));

    motors_enable(true);
    vTaskDelay(pdMS_TO_TICKS(100));   /* let the drivers wake up */

    // while (true) {
    //     ESP_LOGI(TAG, "Performing 1 revolution");

    //     for (int i = 0; i < 200; i++) {
    //         gpio_set_level(PIN_X_STEP, 1);
    //         vTaskDelay(pdMS_TO_TICKS(1000));
    //         gpio_set_level(PIN_X_STEP, 0);
    //         vTaskDelay(pdMS_TO_TICKS(1000));
    //     }

    //     ESP_LOGI(TAG, "Revolution completed, waiting for 1s, then repeating...");
    //     vTaskDelay(pdMS_TO_TICKS(1000));
    // }
    

    while (true) {
        ESP_LOGI(TAG, "X +1 rev");
        ESP_ERROR_CHECK(move_xy(x, y, STEPS_PER_REV, 0));
        vTaskDelay(pdMS_TO_TICKS(300));
        ESP_LOGI(TAG, "X -1 rev");
        ESP_ERROR_CHECK(move_xy(x, y, -STEPS_PER_REV, 0));
        vTaskDelay(pdMS_TO_TICKS(300));

        ESP_LOGI(TAG, "Y +1 rev");
        ESP_ERROR_CHECK(move_xy(x, y, 0, STEPS_PER_REV));
        vTaskDelay(pdMS_TO_TICKS(300));
        ESP_LOGI(TAG, "Y -1 rev");
        ESP_ERROR_CHECK(move_xy(x, y, 0, -STEPS_PER_REV));
        vTaskDelay(pdMS_TO_TICKS(300));

        ESP_LOGI(TAG, "Diagonal (X +2 rev, Y +1 rev)");
        ESP_ERROR_CHECK(move_xy(x, y, 2 * STEPS_PER_REV, STEPS_PER_REV));
        vTaskDelay(pdMS_TO_TICKS(300));
        ESP_LOGI(TAG, "Diagonal (X -2 rev, Y -1 rev)");
        ESP_ERROR_CHECK(move_xy(x, y, -2 * STEPS_PER_REV, -STEPS_PER_REV));

        ESP_LOGI(TAG, "Position X=%ld Y=%ld (should be 0,0)",
                 (long)stepper_get_position(x), (long)stepper_get_position(y));
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
