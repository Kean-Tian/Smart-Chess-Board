#include "scb_core.h"
#include "board_pins.h"
#include <errno.h>
#include <limits.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const unsigned columns[8] = SCB_COLUMN_PINS;
static const unsigned address[3] = {SCB_PIN_ROW_A0, SCB_PIN_ROW_A1, SCB_PIN_ROW_A2};
static void motion_tick(ScbCore *c, int64_t now);

static void emit(ScbCore *c, const char *fmt, ...) {
    char out[SCB_LINE_CAPACITY];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(out, sizeof(out) - 1U, fmt, ap);
    va_end(ap);
    if (n < 0 || (size_t)n >= sizeof(out) - 1U) return;
    out[n] = '\n'; out[n + 1] = 0;
    c->io.emit(c->io.ctx, out);
}

static void reply(ScbCore *c, const char *kind, unsigned id, const char *what) {
    emit(c, "%s %u %s", kind, id, what);
}

static void power_off(ScbCore *c) {
    (void)c->io.write(c->io.ctx, SCB_PIN_MAGNET, false);
    (void)c->io.write(c->io.ctx, SCB_PIN_MOTOR_EN, true);
    (void)c->io.write(c->io.ctx, SCB_PIN_X_STEP, false);
    (void)c->io.write(c->io.ctx, SCB_PIN_Y_STEP, false);
    c->magnet = false;
    c->magnet_wanted = false;
}

void scb_core_fault(ScbCore *c, const char *reason) {
    bool interrupted = c->moving;
    unsigned id = c->move_id;
    power_off(c);
    c->armed = c->moving = c->origin_valid = false;
    c->tracker.initialized = false;
    c->tracker.pending_count = 0;
    if (interrupted) reply(c, "ERR", id, reason);
    emit(c, "FAULT %s", reason);
}

static bool set_row(ScbCore *c, unsigned row) {
    for (unsigned i = 0; i < 3; ++i)
        if (!c->io.write(c->io.ctx, address[i], (row & (1U << i)) != 0)) return false;
    return true;
}

bool scb_core_init(ScbCore *c, ScbIo io, int64_t now) {
    if (!c || !io.write || !io.read || !io.pulse || !io.show_leds || !io.emit) return false;
    memset(c, 0, sizeof(*c)); c->io = io; c->active_low = true;
    /* Must be the first outputs written: motor disable and magnet OFF. */
    if (!io.write(io.ctx, SCB_PIN_MOTOR_EN, true) ||
        !io.write(io.ctx, SCB_PIN_MAGNET, false) ||
        !io.write(io.ctx, SCB_PIN_X_STEP, false) ||
        !io.write(io.ctx, SCB_PIN_Y_STEP, false)) return false;
    scb_led_grid_init(&c->leds);
    c->leds.first_row_is_rank_eight = SCB_LED_REVERSE_ROWS;
    c->leds.first_column_is_file_h = SCB_LED_REVERSE_COLUMNS;
    scb_move_tracker_initialize(&c->tracker);
    if (scb_debouncer_initialize(&c->debounce, SCB_DEBOUNCE_SCANS) < 0 ||
        !set_row(c, 0)) return false;
    c->row_ready_at = now + SCB_SCAN_SETTLE_US;
    if (!io.show_leds(io.ctx, &c->leds)) return false;
    emit(c, "HELLO SCB_ESP32S3 1");
    return true;
}

static void board_report(ScbCore *c, bool raw) {
    uint64_t bits = 0;
    const bool *map = raw ? c->raw_frame : c->stable;
    for (unsigned i = 0; i < 64; ++i) if (map[i]) bits |= UINT64_C(1) << i;
    emit(c, "%s %016llX", raw ? "RAW" : "BOARD", (unsigned long long)bits);
}

static void scan_tick(ScbCore *c, int64_t now) {
    if (now < c->row_ready_at) return;
    for (unsigned col = 0; col < 8; ++col) {
        bool high = c->io.read(c->io.ctx, columns[col]);
        unsigned rank = SCB_SENSOR_REVERSE_ROWS ? 7U - c->row : c->row;
        unsigned file = SCB_SENSOR_REVERSE_COLUMNS ? 7U - col : col;
        c->sampled[rank * 8U + file] = c->active_low ? !high : high;
    }
    if (++c->row == 8) {
        c->row = 0;
        memcpy(c->raw_frame, c->sampled, sizeof(c->raw_frame));
        if (scb_debouncer_update(&c->debounce, c->sampled, c->stable) > 0) {
            c->board_ready = true;
            board_report(c, false);
            /* During commanded robot travel, occupancy is telemetry, not a human move. */
            if (!c->moving && !c->ignore_frames) {
                ScbBoardEvent ev;
                if (scb_move_tracker_process(&c->tracker, c->stable, &ev) == 0)
                    emit(c, "EVENT %s", ev.message);
            }
        }
        if (!c->moving && c->ignore_frames) {
            --c->ignore_frames;
            scb_move_tracker_initialize(&c->tracker);
            if (c->board_ready) {
                ScbBoardEvent ev;
                scb_move_tracker_process(&c->tracker, c->stable, &ev);
            }
        }
    }
    if (!set_row(c, c->row)) { scb_core_fault(c, "GPIO"); return; }
    c->row_ready_at = now + SCB_SCAN_SETTLE_US;
}

static bool integer(const char *s, long lo, long hi, long *v) {
    if (!s || !*s || *s == '+' || *s == ' ') return false;
    char *end; errno = 0; long n = strtol(s, &end, 10);
    if (errno || *end || n < lo || n > hi) return false;
    *v = n; return true;
}

static bool require_armed(ScbCore *c, unsigned id, int64_t now) {
    if (!c->armed || now - c->last_ping >= SCB_LINK_TIMEOUT_US) {
        reply(c, "ERR", id, "NOT_ARMED"); return false;
    }
    if (c->moving) { reply(c, "ERR", id, "BUSY"); return false; }
    return true;
}

static void begin_motion(ScbCore *c, unsigned id, int x, int y, bool carry, int64_t now) {
    bool was_on = c->magnet;
    c->target_x = x; c->target_y = y; c->move_id = id;
    c->magnet_wanted = carry; c->moving = true; c->move_started = now;
    c->next_step_at = now + (carry ? SCB_MAGNET_SETTLE_US : 1000);
    if (!c->io.write(c->io.ctx, SCB_PIN_MAGNET, carry) ||
        !c->io.write(c->io.ctx, SCB_PIN_MOTOR_EN, false)) {
        scb_core_fault(c, "GPIO"); return;
    }
    c->magnet = carry;
    if (carry && !was_on) c->magnet_started = now;
    reply(c, "ACK", id, "MOTION");
}

static void command(ScbCore *c, char *line, int64_t now) {
    char *args[7]; unsigned n = 0, id = 0; char *save = NULL;
    for (char *t = strtok_r(line, " \t\r", &save); t; t = strtok_r(NULL, " \t\r", &save)) {
        if (n == 7) { reply(c, "ERR", 0, "ARGS"); return; }
        args[n++] = t;
    }
    if (!n) return;
    if (args[0][0] == '@') {
        long number;
        if (!integer(args[0] + 1, 0, INT_MAX, &number)) { reply(c, "ERR", 0, "ID"); return; }
        id = (unsigned)number;
        for (unsigned i = 1; i < n; ++i) args[i - 1] = args[i];
        if (!--n) { reply(c, "ERR", id, "ARGS"); return; }
    }
    const char *cmd = args[0];
    if (!strcmp(cmd, "PING") && n == 1) {
        c->last_ping = now; reply(c, "ACK", id, "PING"); return;
    }
    if ((!strcmp(cmd, "STOP") || !strcmp(cmd, "DISARM")) && n == 1) {
        bool busy = c->moving; unsigned old = c->move_id;
        power_off(c); c->armed = c->moving = c->origin_valid = false;
        c->tracker.initialized = false; c->tracker.pending_count = 0;
        if (busy) reply(c, "ERR", old, "STOPPED");
        reply(c, "ACK", id, cmd); return;
    }
    if (!strcmp(cmd, "STATUS") && n == 1) {
        emit(c, "STATUS %u armed=%u moving=%u magnet=%u origin=%u steps=%u", id,
             c->armed, c->moving, c->magnet, c->origin_valid, c->steps_per_tile);
        return;
    }
    if ((!strcmp(cmd, "SCAN") || !strcmp(cmd, "RAW")) && n == 1) {
        if (!c->board_ready) { reply(c, "ERR", id, "NOT_READY"); return; }
        board_report(c, !strcmp(cmd, "RAW")); reply(c, "ACK", id, cmd); return;
    }
    if (!strcmp(cmd, "ARM") && n == 1) {
        if (now - c->last_ping >= SCB_LINK_TIMEOUT_US || c->last_ping == 0) {
            reply(c, "ERR", id, "PING_REQUIRED"); return;
        }
        if (c->moving) { reply(c, "ERR", id, "BUSY"); return; }
        c->armed = true; reply(c, "ACK", id, cmd); return;
    }
    if (!strcmp(cmd, "HOME") && n == 1) {
        reply(c, "ERR", id, "NO_HOME_SWITCHES"); return;
    }
    if (!strcmp(cmd, "SET_STEPS") && n == 2) {
        long steps;
        if (!integer(args[1], 1, SCB_MAX_STEPS_PER_TILE, &steps)) goto bad_args;
        if (c->moving) { reply(c, "ERR", id, "BUSY"); return; }
        c->steps_per_tile = (unsigned)steps; c->origin_valid = false;
        reply(c, "ACK", id, cmd); return;
    }
    if (!strcmp(cmd, "POLARITY") && n == 2) {
        if (c->moving) { reply(c, "ERR", id, "BUSY"); return; }
        if (strcmp(args[1], "LOW") && strcmp(args[1], "HIGH")) goto bad_args;
        c->active_low = !strcmp(args[1], "LOW");
        scb_debouncer_initialize(&c->debounce, SCB_DEBOUNCE_SCANS);
        scb_move_tracker_initialize(&c->tracker); c->board_ready = false; c->row = 0;
        if (!set_row(c, 0)) { scb_core_fault(c, "GPIO"); return; }
        c->row_ready_at = now + SCB_SCAN_SETTLE_US;
        reply(c, "ACK", id, cmd); return;
    }
    if (!strcmp(cmd, "ORIGIN") && n == 2) {
        int sq = scb_square_index(args[1]);
        if (sq < 0) goto bad_args;
        if (c->moving) { reply(c, "ERR", id, "BUSY"); return; }
        if (!c->steps_per_tile) { reply(c, "ERR", id, "CALIBRATE_FIRST"); return; }
        c->x = (sq % 8) * (int)c->steps_per_tile;
        c->y = (sq / 8) * (int)c->steps_per_tile;
        c->origin_valid = true; reply(c, "ACK", id, cmd); return;
    }
    if (!strcmp(cmd, "MAGNET") && n == 2) {
        if (strcmp(args[1], "ON") && strcmp(args[1], "OFF")) goto bad_args;
        bool on = !strcmp(args[1], "ON");
        if (c->moving) { reply(c, "ERR", id, "BUSY"); return; }
        if (on && !require_armed(c, id, now)) return;
        if (!c->io.write(c->io.ctx, SCB_PIN_MAGNET, on)) { scb_core_fault(c, "GPIO"); return; }
        if (on && !c->magnet) c->magnet_started = now;
        c->magnet = on;
        reply(c, "ACK", id, cmd); return;
    }
    if (!strcmp(cmd, "LED_CLEAR") && n == 1) {
        scb_led_clear(&c->leds);
        if (!c->io.show_leds(c->io.ctx, &c->leds)) { reply(c, "ERR", id, "LED"); return; }
        reply(c, "ACK", id, cmd); return;
    }
    if (!strcmp(cmd, "LED") && n == 5) {
        int sq = scb_square_index(args[1]); long r, g, b;
        if (sq < 0 || !integer(args[2], 0, 255, &r) || !integer(args[3], 0, 255, &g) ||
            !integer(args[4], 0, 255, &b)) goto bad_args;
        scb_led_set_square(&c->leds, (unsigned)sq, (ScbRgb){(uint8_t)r, (uint8_t)g, (uint8_t)b});
        if (!c->io.show_leds(c->io.ctx, &c->leds)) { reply(c, "ERR", id, "LED"); return; }
        reply(c, "ACK", id, cmd); return;
    }
    if (!strcmp(cmd, "MARK") && n == 4) {
        int from = scb_square_index(args[1]), to = scb_square_index(args[2]);
        if (from < 0 || to < 0 || (strcmp(args[3], "LEGAL") && strcmp(args[3], "ILLEGAL"))) goto bad_args;
        scb_led_mark_move(&c->leds, (unsigned)from, (unsigned)to, !strcmp(args[3], "LEGAL"));
        if (!c->io.show_leds(c->io.ctx, &c->leds)) { reply(c, "ERR", id, "LED"); return; }
        reply(c, "ACK", id, cmd); return;
    }
    if ((!strcmp(cmd, "GOTO") && n == 2) || (!strcmp(cmd, "MOVE") && n == 3)) {
        bool carry = !strcmp(cmd, "MOVE");
        int from = carry ? scb_square_index(args[1]) : 0;
        int to = scb_square_index(args[carry ? 2 : 1]);
        if (from < 0 || to < 0) goto bad_args;
        if (!require_armed(c, id, now)) return;
        if (!c->steps_per_tile || !c->origin_valid) { reply(c, "ERR", id, "REFERENCE_REQUIRED"); return; }
        if (carry && (c->x != (from % 8) * (int)c->steps_per_tile ||
                      c->y != (from / 8) * (int)c->steps_per_tile)) {
            reply(c, "ERR", id, "SOURCE_NOT_ALIGNED"); return;
        }
        begin_motion(c, id, (to % 8) * (int)c->steps_per_tile,
                     (to / 8) * (int)c->steps_per_tile, carry, now); return;
    }
    if (!strcmp(cmd, "JOG") && n == 3) {
        long steps;
        if ((strcmp(args[1], "X") && strcmp(args[1], "Y")) ||
            !integer(args[2], -SCB_MAX_JOG_STEPS, SCB_MAX_JOG_STEPS, &steps) || !steps) goto bad_args;
        if (!require_armed(c, id, now)) return;
        /* Relative bench calibration. No absolute reference survives a JOG. */
        c->origin_valid = false; c->x = c->y = 0;
        begin_motion(c, id, !strcmp(args[1], "X") ? (int)steps : 0,
                     !strcmp(args[1], "Y") ? (int)steps : 0, false, now); return;
    }
bad_args:
    reply(c, "ERR", id, "COMMAND_OR_ARGS");
}

void scb_core_feed(ScbCore *c, const void *bytes, size_t len, int64_t now) {
    /* A late PING must not conceal an already-expired motion watchdog. */
    motion_tick(c, now);
    const unsigned char *p = bytes;
    for (size_t i = 0; i < len; ++i) {
        unsigned char ch = p[i];
        if (ch == '\n') {
            if (c->discard_line) reply(c, "ERR", 0, "LINE_DROPPED");
            else { c->input[c->input_len] = 0; command(c, c->input, now); }
            c->input_len = 0; c->discard_line = false;
        } else if (!c->discard_line) {
            if ((ch < 32 && ch != '\t' && ch != '\r') || ch > 126 ||
                c->input_len >= sizeof(c->input) - 1U) {
                c->discard_line = true; c->input_len = 0;
            } else c->input[c->input_len++] = (char)ch;
        }
    }
}

static void motion_tick(ScbCore *c, int64_t now) {
    if ((c->armed || c->moving || c->magnet) && now - c->last_ping >= SCB_LINK_TIMEOUT_US) {
        scb_core_fault(c, "LINK_TIMEOUT"); return;
    }
    if (c->magnet && now - c->magnet_started >= SCB_MAGNET_MAX_US) {
        scb_core_fault(c, "MAGNET_TIMEOUT"); return;
    }
    if (!c->moving) return;
    if (now - c->move_started >= SCB_MOVE_TIMEOUT_US) {
        scb_core_fault(c, "MOTION_TIMEOUT"); return;
    }
    if (now < c->next_step_at) return;
    if (c->x == c->target_x && c->y == c->target_y) {
        power_off(c); c->moving = false;
        c->ignore_frames = SCB_DEBOUNCE_SCANS + 1;
        scb_move_tracker_initialize(&c->tracker);
        /* Re-establish tracker baseline even if occupancy has not changed. */
        if (c->board_ready) {
            ScbBoardEvent ev;
            scb_move_tracker_process(&c->tracker, c->stable, &ev);
        }
        reply(c, "DONE", c->move_id, "MOTION");
        if (c->board_ready) board_report(c, false);
        return;
    }
    bool x_axis = c->x != c->target_x;
    int *pos = x_axis ? &c->x : &c->y;
    int target = x_axis ? c->target_x : c->target_y;
    bool positive = target > *pos;
    bool direction = positive != (x_axis ? SCB_INVERT_X_DIR : SCB_INVERT_Y_DIR);
    if (!c->io.write(c->io.ctx, x_axis ? SCB_PIN_X_DIR : SCB_PIN_Y_DIR, direction) ||
        !c->io.pulse(c->io.ctx, x_axis ? SCB_PIN_X_STEP : SCB_PIN_Y_STEP)) {
        scb_core_fault(c, "GPIO"); return;
    }
    *pos += positive ? 1 : -1;
    /* No catch-up pulse burst after scheduling delays. */
    c->next_step_at = now + SCB_STEP_INTERVAL_US;
}

void scb_core_tick(ScbCore *c, int64_t now) {
    motion_tick(c, now);
    scan_tick(c, now);
}
