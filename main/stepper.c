#include "stepper.h"

#include <stdlib.h>

#include "driver/gptimer.h"
#include "esp_attr.h"
#include "esp_check.h"
#include "esp_log.h"
#include "esp_rom_sys.h"
#include "freertos/task.h"

#define STEP_PULSE_US   2u       /* A4988 needs >= 1 us high; 2 us gives margin */
#define TIMER_HZ        1000000u    /* 1 tick = 1 us */
#define MAX_SPEED_LIMIT 20000u      /* keeps the step period well above the 5 us timer limit */

static const char *TAG = "stepper";

struct stepper {
    gpio_num_t step_pin;
    gpio_num_t dir_pin;
    bool invert_dir;
    gptimer_handle_t timer;
    gptimer_alarm_config_t alarm;   /* lives in internal RAM; reused inside the ISR */

    uint32_t v0;        /* start speed, steps/s */
    uint32_t vmax;      /* cruise speed, steps/s */
    uint32_t accel;     /* steps/s^2 */
    uint32_t n_accel;   /* steps needed to go from v0 to vmax */

    volatile bool busy;
    volatile int32_t dir;       /* +1 or -1 */
    volatile int32_t position;
    volatile uint32_t total;    /* steps in the current move */
    volatile uint32_t done;     /* steps already issued */
};

/* Integer square root (bitwise), safe to call from the ISR. */
static inline uint32_t IRAM_ATTR isqrt_u32(uint32_t x)
{
    uint32_t result = 0;
    uint32_t bit = 1u << 30;
    while (bit > x) {
        bit >>= 2;
    }
    while (bit != 0) {
        if (x >= result + bit) {
            x -= result + bit;
            result = (result >> 1) + bit;
        } else {
            result >>= 1;
        }
        bit >>= 2;
    }
    return result;
}

/* Speed (steps/s) to use for the interval that follows `done` issued steps. */
static inline uint32_t IRAM_ATTR speed_for(const struct stepper *s, uint32_t done, uint32_t remaining)
{
    uint32_t n = (done < remaining) ? done : remaining;   /* ramp up from the start, down to the end */
    if (n > s->n_accel) {
        n = s->n_accel;
    }
    uint32_t v = isqrt_u32(s->v0 * s->v0 + 2u * s->accel * n);   /* v^2 = v0^2 + 2*a*n */
    if (v > s->vmax) {
        v = s->vmax;
    }
    if (v < s->v0) {
        v = s->v0;
    }
    return v;
}

static bool IRAM_ATTR stepper_on_alarm(gptimer_handle_t timer, const gptimer_alarm_event_data_t *edata, void *user_ctx)
{
    struct stepper *s = (struct stepper *)user_ctx;

    /* One step pulse. */
    gpio_set_level(s->step_pin, 1);
    esp_rom_delay_us(STEP_PULSE_US);
    gpio_set_level(s->step_pin, 0);

    s->done = s->done + 1u;
    s->position = s->position + s->dir;

    uint32_t remaining = s->total - s->done;
    if (remaining == 0u) {
        gptimer_stop(timer);
        s->busy = false;
        return false;
    }

    uint32_t v = speed_for(s, s->done, remaining);
    s->alarm.alarm_count = edata->alarm_value + (TIMER_HZ / v);   /* no drift from ISR latency */
    gptimer_set_alarm_action(timer, &s->alarm);
    return false;
}

esp_err_t stepper_set_profile(stepper_t *s, uint32_t start_sps, uint32_t max_sps, uint32_t accel_sps2)
{
    ESP_RETURN_ON_FALSE(s != NULL, ESP_ERR_INVALID_ARG, TAG, "null stepper");
    ESP_RETURN_ON_FALSE(start_sps > 0u && max_sps >= start_sps && max_sps <= MAX_SPEED_LIMIT && accel_sps2 > 0u,
                        ESP_ERR_INVALID_ARG, TAG, "bad speed profile");
    ESP_RETURN_ON_FALSE(!s->busy, ESP_ERR_INVALID_STATE, TAG, "axis is moving");

    s->v0 = start_sps;
    s->vmax = max_sps;
    s->accel = accel_sps2;
    uint64_t dv2 = (uint64_t)max_sps * max_sps - (uint64_t)start_sps * start_sps;
    s->n_accel = (uint32_t)(dv2 / (2ull * accel_sps2));
    return ESP_OK;
}

esp_err_t stepper_new(const stepper_config_t *cfg, stepper_t **out)
{
    esp_err_t ret = ESP_OK;
    ESP_RETURN_ON_FALSE(cfg != NULL && out != NULL, ESP_ERR_INVALID_ARG, TAG, "null argument");

    struct stepper *s = (struct stepper *)calloc(1, sizeof(struct stepper));
    ESP_RETURN_ON_FALSE(s != NULL, ESP_ERR_NO_MEM, TAG, "out of memory");

    s->step_pin = cfg->step_pin;
    s->dir_pin = cfg->dir_pin;
    s->invert_dir = cfg->invert_dir;
    s->dir = 1;
    ESP_GOTO_ON_ERROR(stepper_set_profile(s, cfg->start_speed_sps, cfg->max_speed_sps, cfg->accel_sps2),
                      fail, TAG, "profile");

    gpio_config_t io = {
        .pin_bit_mask = (1ULL << cfg->step_pin) | (1ULL << cfg->dir_pin),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_GOTO_ON_ERROR(gpio_config(&io), fail, TAG, "gpio_config");
    gpio_set_level(s->step_pin, 0);
    gpio_set_level(s->dir_pin, 0);

    gptimer_config_t tcfg = {
        .clk_src = GPTIMER_CLK_SRC_DEFAULT,
        .direction = GPTIMER_COUNT_UP,
        .resolution_hz = TIMER_HZ,
    };
    ESP_GOTO_ON_ERROR(gptimer_new_timer(&tcfg, &s->timer), fail, TAG, "new timer");

    gptimer_event_callbacks_t cbs = {
        .on_alarm = stepper_on_alarm,
    };
    /* Callbacks must be registered before gptimer_enable(). */
    ESP_GOTO_ON_ERROR(gptimer_register_event_callbacks(s->timer, &cbs, s), fail_timer, TAG, "callbacks");
    ESP_GOTO_ON_ERROR(gptimer_enable(s->timer), fail_timer, TAG, "enable timer");

    *out = s;
    return ESP_OK;

fail_timer:
    gptimer_del_timer(s->timer);
fail:
    free(s);
    return ret;
}

esp_err_t stepper_move(stepper_t *s, int32_t steps)
{
    ESP_RETURN_ON_FALSE(s != NULL, ESP_ERR_INVALID_ARG, TAG, "null stepper");
    ESP_RETURN_ON_FALSE(!s->busy, ESP_ERR_INVALID_STATE, TAG, "axis is already moving");
    if (steps == 0) {
        return ESP_OK;
    }

    s->dir = (steps > 0) ? 1 : -1;
    bool level = (s->dir > 0) ? !s->invert_dir : s->invert_dir;
    gpio_set_level(s->dir_pin, level ? 1 : 0);   /* DIR settles during the first step interval */
    esp_rom_delay_us(5);

    s->total = (uint32_t)((steps > 0) ? steps : -steps);
    s->done = 0;
    s->busy = true;

    s->alarm.reload_count = 0;
    s->alarm.alarm_count = TIMER_HZ / s->v0;          /* first step after one start-speed interval */
    s->alarm.flags.auto_reload_on_alarm = false;      /* we re-arm the alarm ourselves each step */

    esp_err_t ret = gptimer_set_raw_count(s->timer, 0);
    if (ret == ESP_OK) {
        ret = gptimer_set_alarm_action(s->timer, &s->alarm);
    }
    if (ret == ESP_OK) {
        ret = gptimer_start(s->timer);
    }
    if (ret != ESP_OK) {
        s->busy = false;
    }
    return ret;
}

bool stepper_is_busy(const stepper_t *s)
{
    return s != NULL && s->busy;
}

esp_err_t stepper_wait_idle(stepper_t *s, TickType_t timeout_ticks)
{
    ESP_RETURN_ON_FALSE(s != NULL, ESP_ERR_INVALID_ARG, TAG, "null stepper");
    TickType_t start = xTaskGetTickCount();
    while (s->busy) {
        if (timeout_ticks != portMAX_DELAY && (xTaskGetTickCount() - start) >= timeout_ticks) {
            return ESP_ERR_TIMEOUT;
        }
        vTaskDelay(1);
    }
    return ESP_OK;
}

esp_err_t stepper_stop(stepper_t *s)
{
    ESP_RETURN_ON_FALSE(s != NULL, ESP_ERR_INVALID_ARG, TAG, "null stepper");
    (void)gptimer_stop(s->timer);   /* returns an error if it was already stopped; that is fine */
    s->busy = false;
    return ESP_OK;
}

int32_t stepper_get_position(const stepper_t *s)
{
    return (s != NULL) ? s->position : 0;
}

void stepper_set_position(stepper_t *s, int32_t position)
{
    if (s != NULL && !s->busy) {
        s->position = position;
    }
}
