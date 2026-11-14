#include "motor_bench.h"
#include <errno.h>
#include <limits.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void emit(ScbMotorBench *b, const char *fmt, ...) {
    char line[SCB_BENCH_LINE_CAPACITY]; va_list ap;
    va_start(ap, fmt); int n = vsnprintf(line, sizeof(line) - 1U, fmt, ap); va_end(ap);
    if (n < 0 || (size_t)n >= sizeof(line) - 1U) return;
    line[n] = '\n'; line[n + 1] = '\0'; b->emit(b->emit_ctx, line);
}
static void reply(ScbMotorBench *b, unsigned id, ScbMotorResult r, const char *what) {
    emit(b, "%s %u %s", r == SCB_MOTOR_OK ? "ACK" : "ERR", id,
         r == SCB_MOTOR_OK ? what : scb_motor_result_name(r));
}
static bool number(const char *s, double *n) {
    char *end; errno = 0; *n = strtod(s, &end);
    return *s && !errno && !*end && isfinite(*n);
}
static bool integer(const char *s, long min, long max, long *n) {
    char *end; errno = 0; *n = strtol(s, &end, 10);
    return *s && !errno && !*end && *n >= min && *n <= max;
}
static ScbMotorResult stop(ScbMotorBench *b, const char *reason, bool report_fault) {
    bool busy = b->motor.moving;
    ScbMotorResult r = scb_motor_stop(&b->motor);
    if (busy) emit(b, "ERR %u %s", b->move_id, reason);
    if (report_fault || r != SCB_MOTOR_OK)
        emit(b, "FAULT %s", r == SCB_MOTOR_OK ? reason : "GPIO");
    return r;
}
void scb_motor_bench_init(ScbMotorBench *b, ScbMotorIo io, ScbMotorPins pins,
                         void (*output)(void *, const char *), void *ctx) {
    memset(b, 0, sizeof(*b)); b->io = io; b->pins = pins;
    b->emit = output; b->emit_ctx = ctx; b->config.poll_period_us = SCB_BENCH_POLL_US;
    /* Set safe outputs even while calibration is deliberately absent. */
    b->motor.io = io; b->motor.pins = pins;
    stop(b, "STARTUP", false);
    emit(b, "HELLO SCB_COREXY_S2_BENCH 1");
}
static bool watchdog(ScbMotorBench *b, int64_t now) {
    if (b->motor.enabled && (!b->ping_seen || now < b->last_ping_us ||
        now - b->last_ping_us >= SCB_BENCH_LINK_TIMEOUT_US)) {
        stop(b, "LINK_TIMEOUT", true); return false;
    }
    if (b->motor.moving && now - b->move_started_us >= SCB_BENCH_MOVE_TIMEOUT_US) {
        stop(b, "MOTION_TIMEOUT", true); return false;
    }
    return true;
}
void scb_motor_bench_tick(ScbMotorBench *b, int64_t now) {
    if (!watchdog(b, now)) return;
    if (!b->motor.initialized || b->motor.faulted) return;
    bool busy = b->motor.moving;
    ScbMotorResult r = scb_motor_tick(&b->motor, now);
    if (r != SCB_MOTOR_OK) {
        if (busy) emit(b, "ERR %u %s", b->move_id, scb_motor_result_name(r));
        emit(b, "FAULT %s", scb_motor_result_name(r));
    } else if (busy && !b->motor.moving) emit(b, "DONE %u MOTION", b->move_id);
}
static void command(ScbMotorBench *b, char *line, int64_t now) {
    char *args[7], *save = NULL; unsigned n = 0, id = 0;
    for (char *s = strtok_r(line, " \t\r", &save); s; s = strtok_r(NULL, " \t\r", &save)) {
        if (n == 7) { emit(b, "ERR 0 ARGS"); return; }
        args[n++] = s;
    }
    if (!n) return;
    if (*args[0] == '@') {
        long parsed;
        if (!integer(args[0] + 1, 0, INT_MAX, &parsed)) { emit(b, "ERR 0 ID"); return; }
        id = (unsigned)parsed;
        for (unsigned i = 1; i < n; ++i) args[i - 1] = args[i];
        if (!--n) { emit(b, "ERR %u ARGS", id); return; }
    }
    const char *cmd = args[0];
    if (!strcmp(cmd, "PING") && n == 1) {
        b->ping_seen = true; b->last_ping_us = now; emit(b, "ACK %u PING", id); return;
    }
    if ((!strcmp(cmd, "STOP") || !strcmp(cmd, "DISARM")) && n == 1) {
        reply(b, id, stop(b, "STOPPED", false), cmd); return;
    }
    if (!strcmp(cmd, "STATUS") && n == 1) {
        emit(b, "STATUS %u armed=%u moving=%u origin=%u config=%u fault=%u", id,
             b->motor.enabled, b->motor.moving, b->motor.referenced, b->configured, b->motor.faulted);
        return;
    }
    if (!strcmp(cmd, "POSITION") && n == 1) {
        double x, y; ScbMotorResult r = scb_motor_position(&b->motor, &x, &y);
        if (r == SCB_MOTOR_OK) emit(b, "STATUS %u x_mm=%.6f y_mm=%.6f", id, x, y);
        else reply(b, id, r, cmd);
        return;
    }
    if (!strcmp(cmd, "ARM") && n == 1) {
        if (!b->ping_seen || now - b->last_ping_us >= SCB_BENCH_LINK_TIMEOUT_US) {
            emit(b, "ERR %u PING_REQUIRED", id); return;
        }
        if (b->motor.enabled) { reply(b, id, SCB_MOTOR_BUSY, cmd); return; }
        if (b->configured != 15U) { emit(b, "ERR %u CALIBRATE_FIRST", id); return; }
        ScbMotorResult r = scb_motor_init(&b->motor, b->io, b->pins, &b->config, now);
        if (r == SCB_MOTOR_OK) r = scb_motor_enable(&b->motor);
        reply(b, id, r, cmd); return;
    }
    if (b->motor.moving) { reply(b, id, SCB_MOTOR_BUSY, cmd); return; }
    if (!strcmp(cmd, "ORIGIN") && n == 3) {
        double x, y;
        if (!number(args[1], &x) || !number(args[2], &y)) goto bad;
        reply(b, id, scb_motor_reference(&b->motor, x, y), cmd); return;
    }
    if (!strcmp(cmd, "GOTO") && n == 3) {
        double x, y;
        if (!number(args[1], &x) || !number(args[2], &y)) goto bad;
        ScbMotorResult r = scb_motor_move_to(&b->motor, x, y, now);
        if (r != SCB_MOTOR_OK) { reply(b, id, r, cmd); return; }
    } else if (!strcmp(cmd, "JOG") && n == 3) {
        long steps;
        if ((strcmp(args[1], "A") && strcmp(args[1], "B")) ||
            !integer(args[2], -1000, 1000, &steps) || !steps) goto bad;
        ScbMotorResult r = scb_motor_move_motors(&b->motor,
            !strcmp(args[1], "A") ? (int32_t)steps : 0,
            !strcmp(args[1], "B") ? (int32_t)steps : 0, now);
        if (r != SCB_MOTOR_OK) { reply(b, id, r, cmd); return; }
    } else {
        /* Calibration cannot change while coils are enabled. */
        if (b->motor.enabled) { reply(b, id, SCB_MOTOR_BUSY, cmd); return; }
        double v[4];
        if (n != 3 && n != 5) goto bad;
        for (unsigned i = 1; i < n; ++i) if (!number(args[i], &v[i - 1])) goto bad;
        if (!strcmp(cmd, "MAP") && n == 5) {
            for (unsigned i = 0; i < 4; ++i) if (v[i] != 1 && v[i] != -1) goto bad;
            if (v[0] * v[2] + v[1] * v[3] != 0) goto bad;
            for (unsigned i = 0; i < 4; ++i) b->config.map[i / 2][i % 2] = (int)v[i];
            b->configured |= 1U;
        } else if (!strcmp(cmd, "SCALE") && n == 3 && v[0] > 0 && v[1] > 0) {
            b->config.steps_per_mm[0] = v[0]; b->config.steps_per_mm[1] = v[1];
            b->configured |= 2U;
        } else if (!strcmp(cmd, "LIMITS") && n == 5 && v[0] < v[1] && v[2] < v[3]) {
            b->config.min_mm[0] = v[0]; b->config.max_mm[0] = v[1];
            b->config.min_mm[1] = v[2]; b->config.max_mm[1] = v[3];
            b->configured |= 4U;
        } else if (!strcmp(cmd, "PROFILE") && n == 3 && v[0] > 0 && v[1] > 0) {
            b->config.speed_mm_s = v[0]; b->config.acceleration_mm_s2 = v[1];
            b->configured |= 8U;
        } else goto bad;
        b->motor.referenced = false;
        reply(b, id, SCB_MOTOR_OK, cmd); return;
    }
    b->move_id = id; b->move_started_us = now;
    emit(b, "ACK %u MOTION", id);
    if (!b->motor.moving) emit(b, "DONE %u MOTION", id);
    return;
bad:
    emit(b, "ERR %u COMMAND_OR_ARGS", id);
}
void scb_motor_bench_feed(ScbMotorBench *b, const void *bytes, size_t length, int64_t now) {
    /* An already-expired watchdog is checked before accepting another PING. */
    (void)watchdog(b, now);
    const unsigned char *input = bytes;
    for (size_t i = 0; i < length; ++i) {
        unsigned char ch = input[i];
        if (ch == '\n') {
            if (b->discard) emit(b, "ERR 0 LINE_DROPPED");
            else { b->line[b->length] = '\0'; command(b, b->line, now); }
            b->length = 0; b->discard = false;
        } else if (!b->discard) {
            if ((ch < 32 && ch != '\t' && ch != '\r') || ch > 126 ||
                b->length >= sizeof(b->line) - 1U) { b->discard = true; b->length = 0; }
            else b->line[b->length++] = (char)ch;
        }
    }
}
