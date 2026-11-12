#include "scb/motor_control.h"
#include <limits.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

static bool valid_time(int64_t now) {
    return now >= 0 && now <= INT64_MAX - (int64_t)UINT32_MAX - SCB_MOTOR_EDGE_US;
}
static bool positive(double x) { return isfinite(x) && x > 0; }
static bool pins_valid(ScbMotorPins p) {
    const unsigned pins[] = {p.step[0], p.step[1], p.dir[0], p.dir[1], p.enable};
    for (unsigned i = 0; i < 5; ++i)
        for (unsigned j = i + 1; j < 5; ++j)
            if (pins[i] == pins[j]) return false;
    return true;
}
static bool config_valid(const ScbMotorConfig *c) {
    if (!c || !positive(c->speed_mm_s) || !positive(c->acceleration_mm_s2) ||
        c->poll_period_us < SCB_MOTOR_EDGE_US || c->poll_period_us > UINT32_MAX / 2U)
        return false;
    for (unsigned i = 0; i < 2; ++i) {
        if (!positive(c->steps_per_mm[i]) || !isfinite(c->min_mm[i]) ||
            !isfinite(c->max_mm[i]) || c->min_mm[i] >= c->max_mm[i]) return false;
        for (unsigned j = 0; j < 2; ++j)
            if (c->map[i][j] != 1 && c->map[i][j] != -1) return false;
    }
    return c->map[0][0] * c->map[1][0] + c->map[0][1] * c->map[1][1] == 0;
}
static bool inside(const ScbMotor *m, double x, double y) {
    return isfinite(x) && isfinite(y) &&
        x >= m->config.min_mm[0] && x <= m->config.max_mm[0] &&
        y >= m->config.min_mm[1] && y <= m->config.max_mm[1];
}
static void coordinates(const ScbMotor *m, const int64_t steps[2], double *x, double *y) {
    const ScbMotorConfig *c = &m->config;
    double a = steps[0] / c->steps_per_mm[0], b = steps[1] / c->steps_per_mm[1];
    double det = c->map[0][0] * c->map[1][1] - c->map[0][1] * c->map[1][0];
    *x = m->reference_mm[0] + (c->map[1][1] * a - c->map[0][1] * b) / det;
    *y = m->reference_mm[1] + (c->map[0][0] * b - c->map[1][0] * a) / det;
}
ScbMotorResult scb_motor_stop(ScbMotor *m) {
    if (!m || !m->io.write) return SCB_MOTOR_CONFIG;
    // EN 拉高停用，STEP 拉低。
    bool ok = m->io.write(m->io.ctx, m->pins.enable, true);
    if (!m->io.write(m->io.ctx, m->pins.step[0], false)) ok = false;
    if (!m->io.write(m->io.ctx, m->pins.step[1], false)) ok = false;
    // 停用后清除坐标参考。
    m->enabled = m->moving = m->referenced = m->high[0] = m->high[1] = false;
    if (!ok) m->faulted = true;
    return ok ? SCB_MOTOR_OK : SCB_MOTOR_GPIO;
}
static ScbMotorResult fault(ScbMotor *m, ScbMotorResult reason) {
    ScbMotorResult stopped = scb_motor_stop(m);
    m->faulted = true;
    return stopped == SCB_MOTOR_OK ? reason : stopped;
}
ScbMotorResult scb_motor_init(ScbMotor *m, ScbMotorIo io, ScbMotorPins pins,
                            const ScbMotorConfig *c, int64_t now) {
    if (!m || !io.write || !pins_valid(pins)) return SCB_MOTOR_CONFIG;
    memset(m, 0, sizeof(*m)); m->io = io; m->pins = pins;
    // 初始化先关闭输出。
    if (scb_motor_stop(m) != SCB_MOTOR_OK) return SCB_MOTOR_GPIO;
    if (!config_valid(c) || !valid_time(now)) return SCB_MOTOR_CONFIG;
    m->config = *c;
    if (!io.write(io.ctx, pins.dir[0], false) || !io.write(io.ctx, pins.dir[1], false))
        return fault(m, SCB_MOTOR_GPIO);
    m->initialized = true; m->last_tick_us = now;
    m->low_until_us = now + SCB_MOTOR_EDGE_US;
    return SCB_MOTOR_OK;
}
ScbMotorResult scb_motor_enable(ScbMotor *m) {
    if (!m || !m->initialized || m->faulted) return SCB_MOTOR_CONFIG;
    if (m->moving) return SCB_MOTOR_BUSY;
    if (!m->io.write(m->io.ctx, m->pins.enable, false)) return fault(m, SCB_MOTOR_GPIO);
    m->enabled = true;
    return SCB_MOTOR_OK;
}
ScbMotorResult scb_motor_reference(ScbMotor *m, double x, double y) {
    // 记录人工对准的位置。
    if (!m || !m->initialized || m->faulted) return SCB_MOTOR_CONFIG;
    if (m->moving) return SCB_MOTOR_BUSY;
    if (!inside(m, x, y)) return SCB_MOTOR_LIMIT;
    m->reference_mm[0] = x; m->reference_mm[1] = y;
    m->position[0] = m->position[1] = 0; m->referenced = true;
    return SCB_MOTOR_OK;
}
ScbMotorResult scb_motor_position(const ScbMotor *m, double *x, double *y) {
    if (!m || !x || !y || !m->initialized) return SCB_MOTOR_CONFIG;
    if (!m->referenced) return SCB_MOTOR_REFERENCE;
    coordinates(m, m->position, x, y);
    return SCB_MOTOR_OK;
}
ScbMotorResult scb_motor_profile(ScbMotor *m, double speed, double acceleration) {
    if (!m || !m->initialized || m->faulted || !positive(speed) || !positive(acceleration))
        return SCB_MOTOR_CONFIG;
    if (m->moving) return SCB_MOTOR_BUSY;
    m->config.speed_mm_s = speed; m->config.acceleration_mm_s2 = acceleration;
    return SCB_MOTOR_OK;
}
// 计算加速、匀速、减速时序。
static double event_time(const ScbMotor *m, uint32_t event) {
    if (event <= m->accel_distance) return sqrt(2.0 * event / m->event_acceleration);
    if (event < m->total - m->accel_distance)
        return m->accel_time + (event - m->accel_distance) / m->peak_rate;
    return m->duration - sqrt(2.0 * (m->total - event) / m->event_acceleration);
}
static bool interval(const ScbMotor *m, uint32_t event, uint32_t *us) {
    double duration = ceil((event_time(m, event) - event_time(m, event - 1U)) * 1e6);
    double minimum = 2.0 * m->config.poll_period_us;
    if (!isfinite(duration) || duration > UINT32_MAX) return false;
    *us = (uint32_t)fmax(duration, minimum);
    return true;
}
static ScbMotorResult plan(ScbMotor *m, const int64_t target[2], int64_t now) {
    if (!m || !m->initialized || m->faulted) return SCB_MOTOR_CONFIG;
    if (m->moving) return SCB_MOTOR_BUSY;
    if (!m->enabled) return SCB_MOTOR_DISABLED;
    if (!m->referenced) return SCB_MOTOR_REFERENCE;
    if (!valid_time(now) || now < m->last_tick_us) return fault(m, SCB_MOTOR_TIME);
    double x, y, old_x, old_y;
    for (unsigned i = 0; i < 2; ++i)
        if (target[i] < -SCB_MOTOR_POSITION_LIMIT || target[i] > SCB_MOTOR_POSITION_LIMIT)
            return SCB_MOTOR_LIMIT;
    coordinates(m, target, &x, &y);
    if (!inside(m, x, y)) return SCB_MOTOR_LIMIT;
    coordinates(m, m->position, &old_x, &old_y);
    m->total = m->emitted = 0;
    for (unsigned i = 0; i < 2; ++i) {
        int64_t delta = target[i] - m->position[i];
        m->target[i] = target[i]; m->sign[i] = delta < 0 ? -1 : 1;
        m->magnitude[i] = (uint32_t)(delta < 0 ? -delta : delta);
        m->error[i] = 0;
        if (m->magnitude[i] > m->total) m->total = m->magnitude[i];
    }
    if (!m->total) return SCB_MOTOR_OK;
    double distance = hypot(x - old_x, y - old_y);
    double events_per_mm = m->total / distance;
    m->event_acceleration = m->config.acceleration_mm_s2 * events_per_mm;
    double max_rate = fmin(m->config.speed_mm_s * events_per_mm,
                          1e6 / (2.0 * m->config.poll_period_us));
    if (!positive(distance) || !positive(m->event_acceleration) || !positive(max_rate))
        return SCB_MOTOR_CONFIG;
    m->accel_time = fmin(max_rate / m->event_acceleration,
                         sqrt(m->total / m->event_acceleration));
    m->peak_rate = m->event_acceleration * m->accel_time;
    m->accel_distance = 0.5 * m->peak_rate * m->accel_time;
    m->duration = 2.0 * m->accel_time + (m->total - 2.0 * m->accel_distance) / m->peak_rate;
    uint32_t first, last;
    if (!interval(m, 1, &first) || !interval(m, m->total, &last)) return SCB_MOTOR_CONFIG;
    for (unsigned i = 0; i < 2; ++i)
        if (!m->io.write(m->io.ctx, m->pins.dir[i], m->sign[i] > 0))
            return fault(m, SCB_MOTOR_GPIO);
    m->last_tick_us = now;
    m->rise_at_us = now + first + SCB_MOTOR_EDGE_US;
    m->moving = true;
    return SCB_MOTOR_OK;
}
ScbMotorResult scb_motor_move_to(ScbMotor *m, double x, double y, int64_t now) {
    if (!m || !m->initialized || m->faulted) return SCB_MOTOR_CONFIG;
    if (m->moving) return SCB_MOTOR_BUSY;
    if (!m->enabled) return SCB_MOTOR_DISABLED;
    if (!m->referenced) return SCB_MOTOR_REFERENCE;
    if (!inside(m, x, y)) return SCB_MOTOR_LIMIT;
    // CoreXY：将 X/Y 换算成 A/B 电机步数。
    double delta[] = {x - m->reference_mm[0], y - m->reference_mm[1]};
    int64_t target[2];
    for (unsigned i = 0; i < 2; ++i) {
        double steps = m->config.steps_per_mm[i] *
            (m->config.map[i][0] * delta[0] + m->config.map[i][1] * delta[1]);
        if (!isfinite(steps) || fabs(steps) > SCB_MOTOR_POSITION_LIMIT) return SCB_MOTOR_LIMIT;
        target[i] = (int64_t)llround(steps);
    }
    return plan(m, target, now);
}
ScbMotorResult scb_motor_move_motors(ScbMotor *m, int32_t a, int32_t b, int64_t now) {
    if (!m || !m->initialized) return SCB_MOTOR_CONFIG;
    const int64_t target[] = {m->position[0] + a, m->position[1] + b};
    return plan(m, target, now);
}
ScbMotorResult scb_motor_tick(ScbMotor *m, int64_t now) {
    // 定期推进脉冲，不阻塞等待。
    if (!m || !m->initialized || m->faulted) return SCB_MOTOR_CONFIG;
    if (!valid_time(now) || now < m->last_tick_us) return fault(m, SCB_MOTOR_TIME);
    m->last_tick_us = now;
    if (!m->moving) return SCB_MOTOR_OK;
    if (m->high[0] || m->high[1]) {
        if (now < m->fall_at_us) return SCB_MOTOR_OK;
        for (unsigned i = 0; i < 2; ++i)
            if (m->high[i] && !m->io.write(m->io.ctx, m->pins.step[i], false))
                return fault(m, SCB_MOTOR_GPIO);
        m->high[0] = m->high[1] = false;
        m->low_until_us = now + SCB_MOTOR_EDGE_US;
        // 正常结束保留使能，保持位置。
        if (m->emitted == m->total) m->moving = false;
        return SCB_MOTOR_OK;
    }
    if (now < m->rise_at_us || now < m->low_until_us) return SCB_MOTOR_OK;
    int64_t next[] = {m->position[0], m->position[1]};
    // DDA：按步数比例协调两台电机。
    for (unsigned i = 0; i < 2; ++i) {
        m->error[i] += m->magnitude[i];
        m->high[i] = m->error[i] >= m->total;
        if (m->high[i]) { m->error[i] -= m->total; next[i] += m->sign[i]; }
    }
    double x, y;
    coordinates(m, next, &x, &y);
    // 发脉冲前检查行程。
    if (!inside(m, x, y)) return fault(m, SCB_MOTOR_LIMIT);
    for (unsigned i = 0; i < 2; ++i)
        if (m->high[i] && !m->io.write(m->io.ctx, m->pins.step[i], true))
            return fault(m, SCB_MOTOR_GPIO);
    m->position[0] = next[0]; m->position[1] = next[1]; ++m->emitted;
    m->fall_at_us = now + SCB_MOTOR_EDGE_US;
    if (m->emitted < m->total) {
        uint32_t us;
        if (!interval(m, m->emitted + 1U, &us)) return fault(m, SCB_MOTOR_CONFIG);
        m->rise_at_us = now + us;
    }
    return SCB_MOTOR_OK;
}
const char *scb_motor_result_name(ScbMotorResult r) {
    static const char *const names[] = {"OK", "CONFIG", "BUSY", "NOT_ARMED",
        "REFERENCE_REQUIRED", "LIMIT", "GPIO", "CLOCK"};
    return (unsigned)r < sizeof(names) / sizeof(names[0]) ? names[r] : "UNKNOWN";
}
