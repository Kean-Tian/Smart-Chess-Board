#include "scb_core.h"
#include "board_pins.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    bool pins[49], board[64], fail_pulse;
    unsigned x_pulses, y_pulses, renders;
    char output[65536];
    size_t used;
} Fake;
static bool write_pin(void *v, unsigned pin, bool high) {
    Fake *f = v; assert(pin < 49); f->pins[pin] = high; return true;
}
static bool read_pin(void *v, unsigned pin) {
    Fake *f = v; assert(pin >= 7 && pin <= 14);
    unsigned row = (unsigned)f->pins[4] | ((unsigned)f->pins[5] << 1) | ((unsigned)f->pins[6] << 2);
    return !f->board[row * 8 + pin - 7];
}
static bool pulse(void *v, unsigned pin) {
    Fake *f = v;
    assert(!f->pins[SCB_PIN_MOTOR_EN]);
    if (f->fail_pulse) return false;
    if (pin == SCB_PIN_X_STEP) ++f->x_pulses;
    else { assert(pin == SCB_PIN_Y_STEP); ++f->y_pulses; }
    return true;
}
static bool leds(void *v, const ScbLedGrid *grid) {
    Fake *f = v; assert(grid); ++f->renders; return true;
}
static void emit(void *v, const char *s) {
    Fake *f = v; size_t n = strlen(s); assert(n && s[n - 1] == '\n');
    assert(n + f->used < sizeof(f->output));
    memcpy(f->output + f->used, s, n + 1); f->used += n;
}
static void init(ScbCore *c, Fake *f) {
    memset(f, 0, sizeof(*f));
    assert(scb_core_init(c, (ScbIo){f, write_pin, read_pin, pulse, leds, emit}, 1));
    assert(f->pins[38] && !f->pins[33]);
}
static void cmd(ScbCore *c, const char *s, int64_t now) { scb_core_feed(c, s, strlen(s), now); }
static void ticks(ScbCore *c, int64_t start, int count) {
    for (int i = 1; i <= count; ++i) scb_core_tick(c, start + i * 1000);
}
static void contains(Fake *f, const char *s) { if (!strstr(f->output, s)) { fprintf(stderr, "Missing %s\n%s", s, f->output); assert(0); } }

static void test_board(void) {
    ScbCore c; Fake f; init(&c, &f);
    f.board[0] = f.board[63] = f.board[12] = true;
    ticks(&c, 1, 30);
    assert(c.board_ready); contains(&f, "BOARD 8000000000001001\n");
    f.board[12] = false; ticks(&c, 30001, 30); contains(&f, "EVENT LIFT e2\n");
    f.board[28] = true; ticks(&c, 60001, 30); contains(&f, "EVENT MOVE e2e4\n");
    cmd(&c, "@4 SCAN\n", 91000); contains(&f, "ACK 4 SCAN\n");
    cmd(&c, "@5 RAW\n", 92000); contains(&f, "RAW 8000000010000001\n");
    cmd(&c, "POLARITY HIGH\n", 93000); assert(!c.board_ready);
    ticks(&c, 93000, 30); assert(c.stable[1] && !c.stable[0]);
}
static void test_protocol(void) {
    ScbCore c; Fake f; init(&c, &f);
    cmd(&c, "@7 PI", 100); cmd(&c, "NG\r\n", 200); contains(&f, "ACK 7 PING\n");
    cmd(&c, "@8 LED a1 20 0 0\n", 300); assert(c.leds.pixels[0].red == 20);
    unsigned renders = f.renders;
    cmd(&c, "@9 LED a1 256 0 0\n", 400); assert(f.renders == renders);
    contains(&f, "ERR 9 COMMAND_OR_ARGS\n");
    cmd(&c, "@10 LED_CLEAR extra\n", 500); assert(f.renders == renders);
    cmd(&c, "@11 SET_STEPS 0\n@12 SET_STEPS 9999999999999999999999\n", 600);
    assert(!c.steps_per_tile);
    char longline[300]; memset(longline, 'X', sizeof(longline));
    scb_core_feed(&c, longline, sizeof(longline), 700);
    cmd(&c, "MAGNET ON\n@13 STATUS\n", 800);
    assert(!c.magnet); contains(&f, "ERR 0 LINE_DROPPED\n"); contains(&f, "STATUS 13");
    const char nul[] = "MAGNET ON\0\n";
    scb_core_feed(&c, nul, sizeof(nul)-1, 900); assert(!c.magnet);
    cmd(&c, "@-1 ARM\n", 1000); assert(!c.armed);
}
static void arm(ScbCore *c) { cmd(c, "PING\nARM\nSET_STEPS 3\nORIGIN a1\n", 1000); assert(c->armed && c->origin_valid); }
static void test_motion(void) {
    ScbCore c; Fake f; init(&c, &f);
    cmd(&c, "@1 MOVE a1 b1\n", 10); contains(&f, "ERR 1 NOT_ARMED\n");
    arm(&c); cmd(&c, "@2 GOTO b1\n", 2000); ticks(&c, 2000, 45);
    assert(f.x_pulses == 3 && !f.y_pulses && c.x == 3);
    assert(!c.moving && f.pins[38]); contains(&f, "DONE 2 MOTION\n");
    cmd(&c, "@3 MOVE a1 a2\n", 49000); contains(&f, "ERR 3 SOURCE_NOT_ALIGNED\n");
    cmd(&c, "@4 MOVE b1 b2\n", 50000); assert(c.magnet && !f.pins[38]);
    ticks(&c, 50000, 150); assert(f.y_pulses == 3 && !c.moving && !c.magnet);
    contains(&f, "DONE 4 MOTION\n");
    cmd(&c, "HOME\n", 201000); contains(&f, "NO_HOME_SWITCHES");
    cmd(&c, "@5 GOTO h8\n@6 STOP\n", 202000);
    assert(!c.armed && !c.moving && !c.origin_valid && !c.magnet && f.pins[38]);
    contains(&f, "ERR 5 STOPPED\n"); contains(&f, "ACK 6 STOP\n");
}
static void test_watchdogs(void) {
    ScbCore c; Fake f; init(&c, &f); arm(&c);
    cmd(&c, "@21 MOVE a1 h8\n", 2000);
    /* Late PING does not rescue stale armed/motion state. */
    cmd(&c, "@22 PING\n", 3000000);
    assert(!c.armed && !c.moving && !c.magnet && f.pins[38]);
    contains(&f, "ERR 21 LINK_TIMEOUT\n");
    init(&c, &f); arm(&c); cmd(&c, "MAGNET ON\n", 2000);
    for (int i = 1; i <= 6; ++i) {
        cmd(&c, "PING\n", i * 1000000);
        if (i < 5) cmd(&c, "MAGNET ON\n", i * 1000000);
        scb_core_tick(&c, i * 1000000);
    }
    assert(!c.magnet && !c.armed); contains(&f, "FAULT MAGNET_TIMEOUT\n");
    init(&c, &f); arm(&c); f.fail_pulse = true;
    cmd(&c, "GOTO b1\n", 2000); scb_core_tick(&c, 4000);
    assert(!c.moving && !c.armed && f.pins[38]); contains(&f, "FAULT GPIO\n");
}
static void test_ambiguous_and_led_mapping(void) {
    ScbMoveTracker t; ScbBoardEvent e; bool b[64] = {0};
    b[4] = b[7] = true; scb_move_tracker_initialize(&t);
    assert(!scb_move_tracker_process(&t, b, &e));
    b[4] = b[7] = false; b[5] = b[6] = true;
    assert(!scb_move_tracker_process(&t, b, &e)); assert(e.kind == SCB_EVENT_AMBIGUOUS);
    ScbLedGrid g; scb_led_grid_init(&g);
    assert(scb_led_index(&g, 0) == 0 && scb_led_index(&g, 8) == 15);
    assert(scb_led_set_square(&g, 64, (ScbRgb){0}) == -1);
    assert(scb_led_mark_move(&g, 12, 28, true) == 0);
    assert(g.pixels[scb_led_index(&g, 12)].blue == 20);
    assert(g.pixels[scb_led_index(&g, 28)].green == 20);
}
int main(void) {
    test_board(); test_protocol(); test_motion(); test_watchdogs(); test_ambiguous_and_led_mapping();
    puts("ESP32 portable-core tests passed: sensing, framing, outputs, motion, watchdogs.");
}
