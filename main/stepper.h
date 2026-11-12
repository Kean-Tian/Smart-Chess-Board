#pragma once
/*
 * Minimal step/dir stepper driver for A4988-style drivers.
 * One GPTimer per axis generates the step pulses with a trapezoidal speed profile.
 * Integer math only inside the ISR.
 */
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct stepper stepper_t;

typedef struct {
    gpio_num_t step_pin;
    gpio_num_t dir_pin;
    bool invert_dir;
    uint32_t start_speed_sps; /* first-step speed, steps per second (>0) */
    uint32_t max_speed_sps;   /* cruise speed, steps per second (>= start speed) */
    uint32_t accel_sps2;      /* acceleration and deceleration, steps per second^2 (>0) */
} stepper_config_t;

esp_err_t stepper_new(const stepper_config_t *cfg, stepper_t **out);

/* Change the speed profile. Only allowed while the axis is idle. */
esp_err_t stepper_set_profile(stepper_t *s, uint32_t start_sps, uint32_t max_sps, uint32_t accel_sps2);

/* Start a relative move (positive/negative). Returns immediately. */
esp_err_t stepper_move(stepper_t *s, int32_t steps);

bool stepper_is_busy(const stepper_t *s);
esp_err_t stepper_wait_idle(stepper_t *s, TickType_t timeout_ticks);

/* Immediate stop (no deceleration). Position stays valid up to the last pulse. */
esp_err_t stepper_stop(stepper_t *s);

/* Position in steps since power-up (or the last set_position call). */
int32_t stepper_get_position(const stepper_t *s);
void stepper_set_position(stepper_t *s, int32_t position);

#ifdef __cplusplus
}
#endif
