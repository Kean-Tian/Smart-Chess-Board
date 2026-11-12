#include "scb/motor_control.h"
#include "motor_bench.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

/* Simulation values ONLY. They do not describe our mechanism or a GPIO map. */
static const ScbMotorPins pins = {.step = {0, 1}, .dir = {2, 3}, .enable = 4};
typedef struct {
    bool pin[5];
    int fail_pin;
    bool fail_high;
    unsigned writes, rises[2], falls[2];
    int64_t now, changed[5], rise_time[4096];
    unsigned rise_events;
    char output[65536];
} Fake;
static bool write_pin(void *ctx, unsigned pin, bool high) {
    Fake *f = ctx; assert(pin < 5);
    if (!f->writes++) assert(pin == pins.enable && high);
    if ((int)pin == f->fail_pin && high == f->fail_high) return false;
    if (pin < 2 && f->pin[pin] != high) {
        if (high) {
            assert(!f->pin[pins.enable]);
            assert(f->now - f->changed[pin] >= SCB_MOTOR_EDGE_US);
            assert(f->now - f->changed[pins.dir[pin]] >= SCB_MOTOR_EDGE_US);
            if (f->rise_events == 0 || f->rise_time[f->rise_events - 1] != f->now) {
                assert(f->rise_events < 4096);
                f->rise_time[f->rise_events++] = f->now;
            }
            ++f->rises[pin];
        } else {
            /* An emergency disable may truncate the final pulse. */
            assert(f->pin[pins.enable] || f->now - f->changed[pin] >= SCB_MOTOR_EDGE_US);
            ++f->falls[pin];
        }
    }
    if (f->pin[pin] != high) f->changed[pin] = f->now;
    f->pin[pin] = high;
    return true;
}
static void output(void *ctx, const char *s) {
    Fake *f = ctx;
    assert(strlen(f->output) + strlen(s) < sizeof(f->output));
    strcat(f->output, s);
}
static ScbMotorConfig config(void) {
    return (ScbMotorConfig){.map = {{1, 1}, {1, -1}}, .steps_per_mm = {10, 10},
        .min_mm = {-20, -20}, .max_mm = {20, 20},
        .speed_mm_s = 10, .acceleration_mm_s2 = 20, .poll_period_us = 1000};
}
static void init(ScbMotor *m, Fake *f, const ScbMotorConfig *c) {
    memset(f, 0, sizeof(*f)); f->fail_pin = -1;
    assert(scb_motor_init(m, (ScbMotorIo){f, write_pin}, pins, c, 0) == SCB_MOTOR_OK);
    assert(f->pin[pins.enable] && !f->pin[0] && !f->pin[1]);
    assert(!m->enabled && !m->referenced && !m->moving && !f->rises[0] && !f->rises[1]);
}
static void reference(ScbMotor *m) {
    assert(scb_motor_enable(m) == SCB_MOTOR_OK);
    assert(scb_motor_reference(m, 0, 0) == SCB_MOTOR_OK);
}
static void finish(ScbMotor *m, Fake *f) {
    unsigned calls = 0;
    while (m->moving) {
        f->now += m->config.poll_period_us;
        assert(scb_motor_tick(m, f->now) == SCB_MOTOR_OK);
        assert(++calls < 100000);
    }
    assert(!f->pin[0] && !f->pin[1] && m->enabled && m->referenced);
}
static void position(ScbMotor *m, double x, double y) {
    double actual_x, actual_y;
    assert(scb_motor_position(m, &actual_x, &actual_y) == SCB_MOTOR_OK);
    assert(fabs(actual_x - x) < 1e-9 && fabs(actual_y - y) < 1e-9);
}
static void test_startup_and_calibration(void) {
    ScbMotor m; Fake f; ScbMotorConfig c = config(); init(&m, &f, &c);
    assert(scb_motor_move_to(&m, 1, 1, 0) == SCB_MOTOR_DISABLED);
    assert(scb_motor_enable(&m) == SCB_MOTOR_OK);
    assert(scb_motor_move_to(&m, 1, 1, 0) == SCB_MOTOR_REFERENCE);
    for (unsigned i = 0; i < 7; ++i) {
        c = config();
        if (i == 0) c.map[0][0] = 0;
        if (i == 1) c.map[1][1] = 1; /* Singular, not CoreXY. */
        if (i == 2) c.steps_per_mm[0] = 0;
        if (i == 3) c.speed_mm_s = NAN;
        if (i == 4) c.acceleration_mm_s2 = -1;
        if (i == 5) c.min_mm[1] = c.max_mm[1];
        if (i == 6) c.poll_period_us = 0;
        assert(scb_motor_stop(&m) == SCB_MOTOR_OK);
        assert(scb_motor_init(&m, (ScbMotorIo){&f, write_pin}, pins, &c, f.now) == SCB_MOTOR_CONFIG);
        assert(f.pin[pins.enable] && !f.pin[0] && !f.pin[1]);
        assert(scb_motor_enable(&m) == SCB_MOTOR_CONFIG);
    }
}
static void test_cartesian_and_independent_motors(void) {
    ScbMotor m; Fake f; ScbMotorConfig c = config(); init(&m, &f, &c); reference(&m);
    assert(scb_motor_move_to(&m, 1, 0, f.now) == SCB_MOTOR_OK);
    assert(f.pin[pins.dir[0]] && f.pin[pins.dir[1]]);
    finish(&m, &f); position(&m, 1, 0);
    assert(f.rises[0] == 10 && f.rises[1] == 10);
    assert(scb_motor_move_to(&m, 1, 1, f.now) == SCB_MOTOR_OK);
    assert(f.pin[pins.dir[0]] && !f.pin[pins.dir[1]]);
    finish(&m, &f); position(&m, 1, 1);
    assert(f.rises[0] == 20 && f.rises[1] == 20);
    assert(scb_motor_move_to(&m, 0, 0, f.now) == SCB_MOTOR_OK);
    finish(&m, &f); position(&m, 0, 0);
    assert(f.rises[0] == 40 && f.rises[1] == 20); /* Diagonal: A only. */
    assert(scb_motor_move_motors(&m, 0, 10, f.now) == SCB_MOTOR_OK);
    finish(&m, &f); position(&m, 0.5, -0.5);
    assert(f.rises[0] == 40 && f.rises[1] == 30);
    assert(f.rises[0] == f.falls[0] && f.rises[1] == f.falls[1]);
}
static void test_all_mappings_and_dda(void) {
    for (int ax = -1; ax <= 1; ax += 2) for (int ay = -1; ay <= 1; ay += 2)
        for (int bx = -1; bx <= 1; bx += 2) {
            ScbMotor m; Fake f; ScbMotorConfig c = config();
            c.map[0][0] = ax; c.map[0][1] = ay;
            c.map[1][0] = bx; c.map[1][1] = -ax * bx * ay;
            init(&m, &f, &c); reference(&m);
            assert(scb_motor_move_to(&m, 0.7, -0.2, 0) == SCB_MOTOR_OK);
            finish(&m, &f); position(&m, 0.7, -0.2);
            assert(m.position[0] == ax * 7 - ay * 2);
            assert(m.position[1] == bx * 7 - c.map[1][1] * 2);
            assert(scb_motor_move_to(&m, 0, 0, f.now) == SCB_MOTOR_OK);
            finish(&m, &f); position(&m, 0, 0);
        }
    ScbMotor m; Fake f; ScbMotorConfig c = config(); c.steps_per_mm[1] = 20;
    init(&m, &f, &c); reference(&m);
    assert(scb_motor_move_to(&m, 0.8, 0.2, 0) == SCB_MOTOR_OK);
    finish(&m, &f); position(&m, 0.8, 0.2);
    assert(f.rises[0] == 10 && f.rises[1] == 12);
    /* Absolute rounding must not accumulate relative rounding drift. */
    assert(scb_motor_move_to(&m, 0.81, 0.21, f.now) == SCB_MOTOR_OK);
    finish(&m, &f); position(&m, 0.8, 0.2);
}
static void test_limits_stop_and_failures(void) {
    ScbMotor m; Fake f; ScbMotorConfig c = config(); init(&m, &f, &c); reference(&m);
    assert(scb_motor_move_to(&m, 21, 0, 0) == SCB_MOTOR_LIMIT);
    assert(scb_motor_move_to(&m, NAN, 0, 0) == SCB_MOTOR_LIMIT);
    assert(scb_motor_move_motors(&m, INT32_MAX, 0, 0) == SCB_MOTOR_LIMIT);
    assert(!m.moving && !f.rises[0]);
    assert(scb_motor_move_to(&m, 2, 1, 0) == SCB_MOTOR_OK);
    assert(scb_motor_reference(&m, 1, 1) == SCB_MOTOR_BUSY);
    assert(scb_motor_profile(&m, 1, 1) == SCB_MOTOR_BUSY);
    assert(scb_motor_move_to(&m, 0, 0, 0) == SCB_MOTOR_BUSY);
    f.now = m.rise_at_us; assert(scb_motor_tick(&m, f.now) == SCB_MOTOR_OK);
    unsigned pulses = f.rises[0] + f.rises[1]; assert(pulses);
    assert(scb_motor_stop(&m) == SCB_MOTOR_OK);
    f.now += 100000; assert(scb_motor_tick(&m, f.now) == SCB_MOTOR_OK);
    assert(f.rises[0] + f.rises[1] == pulses && !m.referenced && f.pin[pins.enable]);
    reference(&m);
    assert(scb_motor_move_to(&m, 1, 0, f.now) == SCB_MOTOR_OK);
    f.fail_pin = (int)pins.step[1]; f.fail_high = true;
    f.now = m.rise_at_us;
    assert(scb_motor_tick(&m, f.now) == SCB_MOTOR_GPIO);
    assert(!m.moving && !m.referenced && f.pin[pins.enable] && !f.pin[0] && !f.pin[1]);
    assert(scb_motor_enable(&m) == SCB_MOTOR_CONFIG);
    /* Falling STEP write failure and disable failure are also surfaced. */
    init(&m, &f, &c); reference(&m);
    assert(scb_motor_move_to(&m, 1, 0, 0) == SCB_MOTOR_OK);
    f.now = m.rise_at_us; assert(scb_motor_tick(&m, f.now) == SCB_MOTOR_OK);
    f.fail_pin = 0; f.fail_high = false; f.now += 1000;
    assert(scb_motor_tick(&m, f.now) == SCB_MOTOR_GPIO);
    assert(f.pin[pins.enable] && !f.pin[1] && !m.referenced);
    f.fail_pin = (int)pins.enable; f.fail_high = true;
    assert(scb_motor_stop(&m) == SCB_MOTOR_GPIO);
}
static void test_intermediate_limits(void) {
    ScbMotor m; Fake f; ScbMotorConfig c = config();
    c.steps_per_mm[1] = 20; c.min_mm[1] = 0;
    init(&m, &f, &c); reference(&m);
    /* Rounded endpoint is inside, but unequal motor scales can make the first
     * DDA event cross the lower Y boundary. It must stop BEFORE that pulse. */
    assert(scb_motor_move_to(&m, 1, 0, 0) == SCB_MOTOR_OK);
    f.now = m.rise_at_us;
    assert(scb_motor_tick(&m, f.now) == SCB_MOTOR_LIMIT);
    assert(!f.rises[0] && !f.rises[1] && !m.referenced && f.pin[pins.enable]);
}
static void test_timing_and_profile(void) {
    ScbMotor m; Fake f; ScbMotorConfig c = config(); init(&m, &f, &c); reference(&m);
    assert(scb_motor_move_to(&m, 10, 0, 0) == SCB_MOTOR_OK);
    int64_t first = m.rise_at_us;
    f.now = first - 1; assert(scb_motor_tick(&m, f.now) == SCB_MOTOR_OK);
    assert(!f.rises[0]);
    f.now = first; assert(scb_motor_tick(&m, f.now) == SCB_MOTOR_OK);
    assert(f.rises[0] == 1);
    assert(scb_motor_tick(&m, f.now) == SCB_MOTOR_OK); /* Same time cannot shorten HIGH. */
    assert(f.pin[0]);
    f.now += 4; assert(scb_motor_tick(&m, f.now) == SCB_MOTOR_OK); assert(f.pin[0]);
    ++f.now; assert(scb_motor_tick(&m, f.now) == SCB_MOTOR_OK); assert(!f.pin[0]);
    finish(&m, &f);
    assert(f.rise_events == 100);
    int64_t early = f.rise_time[1] - f.rise_time[0];
    int64_t middle = f.rise_time[50] - f.rise_time[49];
    int64_t late = f.rise_time[99] - f.rise_time[98];
    assert(early > middle && late > middle);
    assert(f.now >= 1500000); /* 10 mm, 10 mm/s, 20 mm/s2 trapezoid. */
    assert(scb_motor_profile(&m, 1e5, 1e6) == SCB_MOTOR_OK);
    unsigned before = f.rise_events;
    assert(scb_motor_move_to(&m, 0, 0, f.now) == SCB_MOTOR_OK);
    finish(&m, &f);
    for (unsigned i = before + 1; i < f.rise_events; ++i)
        assert(f.rise_time[i] - f.rise_time[i - 1] >= 2000);
    assert(scb_motor_move_to(&m, 1, 0, f.now) == SCB_MOTOR_OK);
    f.now += 1000000; before = f.rises[0];
    assert(scb_motor_tick(&m, f.now) == SCB_MOTOR_OK);
    assert(f.rises[0] == before + 1); /* Delayed tick emits one event, no burst. */
    assert(scb_motor_tick(&m, f.now - 1) == SCB_MOTOR_TIME);
    assert(!m.referenced && !m.enabled);
}
static void feed(ScbMotorBench *b, Fake *f, const char *cmd, int64_t now) {
    f->now = now; scb_motor_bench_feed(b, cmd, strlen(cmd), now);
}
static void contains(Fake *f, const char *text) { assert(strstr(f->output, text)); }
static void bench_init(ScbMotorBench *b, Fake *f) {
    memset(f, 0, sizeof(*f)); f->fail_pin = -1;
    scb_motor_bench_init(b, (ScbMotorIo){f, write_pin}, pins, output, f);
}
static void bench_arm(ScbMotorBench *b, Fake *f) {
    feed(b, f, "MAP 1 1 1 -1\nSCALE 10 10\nLIMITS -20 20 -20 20\nPROFILE 10 20\nPING\nARM\nORIGIN 0 0\n", f->now);
    assert(b->motor.enabled && b->motor.referenced);
}
static void test_bench_protocol_and_watchdogs(void) {
    ScbMotorBench b; Fake f; bench_init(&b, &f);
    feed(&b, &f, "@1 ARM\nPING\n@2 ARM\n", 1000);
    contains(&f, "ERR 1 PING_REQUIRED\n"); contains(&f, "ERR 2 CALIBRATE_FIRST\n");
    assert(f.pin[pins.enable] && !f.rises[0]);
    feed(&b, &f, "MAP 1 1 1 1\nSCALE nan 10\nLIMITS 1 0 0 1\nPROFILE 0 1\n", 1000);
    assert(b.configured == 0);
    bench_arm(&b, &f);
    feed(&b, &f, "@3 GO", 2000); feed(&b, &f, "TO 1 0\r\n", 2000);
    contains(&f, "ACK 3 MOTION\n");
    for (int i = 3; b.motor.moving; ++i) {
        f.now = i * 1000; scb_motor_bench_tick(&b, f.now); assert(i < 2000);
    }
    contains(&f, "DONE 3 MOTION\n"); position(&b.motor, 1, 0);
    feed(&b, &f, "@4 JOG B -1\n@5 STOP\n", f.now);
    contains(&f, "ERR 4 STOPPED\n"); contains(&f, "ACK 5 STOP\n");
    assert(!b.motor.enabled && !b.motor.referenced);
    bench_arm(&b, &f); feed(&b, &f, "@6 GOTO 10 0\n", f.now);
    feed(&b, &f, "@7 PING\n", f.now + SCB_BENCH_LINK_TIMEOUT_US);
    contains(&f, "ERR 6 LINK_TIMEOUT\n"); contains(&f, "FAULT LINK_TIMEOUT\n");
    assert(!b.motor.enabled && !b.motor.referenced);
    bench_arm(&b, &f);
    feed(&b, &f, "@8 GOTO 0 0\n", f.now); contains(&f, "DONE 8 MOTION\n");
    feed(&b, &f, "@9 GOTO 10 0\n", f.now);
    for (unsigned i = 0; i < 30; ++i) feed(&b, &f, "PING\n", f.now + 1000000);
    contains(&f, "ERR 9 MOTION_TIMEOUT\n"); assert(!b.motor.enabled);
    char longline[200]; memset(longline, 'X', sizeof(longline));
    scb_motor_bench_feed(&b, longline, sizeof(longline), f.now);
    feed(&b, &f, "ARM\n", f.now); contains(&f, "ERR 0 LINE_DROPPED\n");
    assert(!b.motor.enabled);
    const char nul[] = "ARM\0\n";
    scb_motor_bench_feed(&b, nul, sizeof(nul) - 1U, f.now); assert(!b.motor.enabled);
    feed(&b, &f, "@-1 ARM\n", f.now); contains(&f, "ERR 0 ID\n");
}
int main(void) {
    test_startup_and_calibration(); test_cartesian_and_independent_motors();
    test_all_mappings_and_dda(); test_limits_stop_and_failures();
    test_intermediate_limits(); test_timing_and_profile(); test_bench_protocol_and_watchdogs();
    puts("CoreXY motor tests passed (simulated GPIO, timing, limits, bench protocol and watchdogs).");
}
