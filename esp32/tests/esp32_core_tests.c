#include "scb_core.h"
#include "board_pins.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    bool pins[SCB_GPIO_COUNT], board[64], fail_pulse;
    unsigned x_pulses, y_pulses, renders;
    char output[65536];
    size_t used;
} Fake;
static bool write_pin(void *v, unsigned pin, bool high) {
    Fake *f = v; assert(pin < SCB_GPIO_COUNT); f->pins[pin] = high; return true;
}
static bool read_pin(void *v, unsigned pin) {
    Fake *f = v;
    const unsigned columns[] = SCB_COLUMN_PINS;
    unsigned col = 0;
    while (col < 8 && columns[col] != pin) ++col;
    assert(col < 8);
    unsigned row = (unsigned)f->pins[SCB_PIN_ROW_A0] |
                   ((unsigned)f->pins[SCB_PIN_ROW_A1] << 1) |
                   ((unsigned)f->pins[SCB_PIN_ROW_A2] << 2);
    /* Model the measured sensor behavior independently of firmware polarity:
       a placed magnet produces a HIGH digital output. */
    return f->board[row * 8 + col];
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
    assert(scb_core_init(c, (ScbIo){.ctx = f, .write = write_pin, .read = read_pin,
        .pulse = pulse, .show_leds = leds, .emit = emit}, 1));
    assert(f->pins[SCB_PIN_MOTOR_EN] && !f->pins[SCB_PIN_MAGNET]);
    assert(!c->active_low);
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
    cmd(&c, "POLARITY LOW\n", 93000); assert(!c.board_ready);
    ticks(&c, 93000, 30); assert(c.stable[1] && !c.stable[0]);
    cmd(&c, "POLARITY HIGH\n", 124000);
    ticks(&c, 124000, 30); assert(!c.stable[1] && c.stable[0]);
}
static void test_scan_covers_all_64_squares(void) {
    ScbCore c; Fake f; init(&c, &f);
    int64_t now = 1;
    for (unsigned square = 0; square < 64; ++square) {
        memset(f.board, 0, sizeof(f.board));
        f.board[square] = true;
        ticks(&c, now, 40);
        now += 40000;
        assert(c.board_ready);
        for (unsigned other = 0; other < 64; ++other)
            assert(c.stable[other] == (other == square));
        char expected[40];
        snprintf(expected, sizeof(expected), "BOARD %016llX\n", 1ULL << square);
        contains(&f, expected);
    }
    memset(f.board, 0, sizeof(f.board));
    ticks(&c, now, 40);
    for (unsigned square = 0; square < 64; ++square) assert(!c.stable[square]);
    contains(&f, "BOARD 0000000000000000\n");
}
static unsigned sensor_lines(const Fake *f) {
    unsigned count = 0;
    const char *cursor = f->output;
    while ((cursor = strstr(cursor, "SENSOR ")) != NULL) { ++count; cursor += 7; }
    return count;
}
static void test_sensor_traces_use_the_accepted_frame(void) {
    ScbCore c; Fake f; init(&c, &f);
    f.board[7] = f.board[16] = true; /* h1 and a3. */
    ticks(&c, 1, 33);
    assert(c.row != 0); /* The scanner has already switched away from row 0. */
    contains(&f, "SENSOR frame=2 mux=000 A0=36:0 A1=37:0 A2=38:0 inputs=00000001 occupy=0000000000010080 polarity=HIGH\n");
    contains(&f, "mux=010 A0=36:0 A1=37:1 A2=38:0 inputs=10000000 occupy=0000000000010080 polarity=HIGH\n");
    assert(sensor_lines(&f) == 2); /* Only occupied rows are reported. */

    f.used = 0; f.output[0] = '\0';
    f.board[7] = false; f.board[63] = true;
    ticks(&c, 33001, 40);
    assert(c.sensor_trace_pending && sensor_lines(&f) == 0);
    ticks(&c, 73001, 160);
    assert(!c.sensor_trace_pending && sensor_lines(&f) == 2);
    contains(&f, "mux=111 A0=36:1 A1=37:1 A2=38:1 inputs=00000001 occupy=8000000000010000 polarity=HIGH\n");

    f.used = 0; f.output[0] = '\0';
    cmd(&c, "@55 SCAN\n", 233500);
    assert(sensor_lines(&f) == 2); /* Explicit SCAN bypasses rate limiting. */
    contains(&f, "BOARD 8000000000010000\n");
    contains(&f, "ACK 55 SCAN\n");

    f.used = 0; f.output[0] = '\0';
    memset(f.board, 0, sizeof(f.board));
    ticks(&c, 233001, 40);
    assert(sensor_lines(&f) == 0 && !c.sensor_trace_pending);
    contains(&f, "BOARD 0000000000000000\n");

    f.used = 0; f.output[0] = '\0';
    f.board[0] = true;
    cmd(&c, "POLARITY LOW\n", 274000);
    ticks(&c, 274000, 30);
    contains(&f, "inputs=10000000 occupy=FFFFFFFFFFFFFFFE polarity=LOW\n");
    assert(sensor_lines(&f) == 8);
    const char *start = f.output, *end;
    while ((end = strchr(start, '\n')) != NULL) {
        assert((size_t)(end - start) < SCB_LINE_CAPACITY);
        start = end + 1;
    }
}
static void test_protocol(void) {
    ScbCore c; Fake f; init(&c, &f);
    contains(&f, "HELLO SCB_S2_SAOLA_1 1\n");
    cmd(&c, "@6 STATUS\n", 50); contains(&f, "polarity=HIGH\n");
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
static void test_live_inputs_do_not_drive_sensor_outputs(void) {
    ScbCore c; Fake f; init(&c, &f);
    bool pins_before[SCB_GPIO_COUNT];
    memcpy(pins_before, f.pins, sizeof(pins_before));
    cmd(&c, "@41 INPUTS\n", 100);
    contains(&f, "STATUS 41 inputs=00000000\n");
    f.board[0] = f.board[7] = true;
    cmd(&c, "@42 INPUTS\n", 200);
    contains(&f, "STATUS 42 inputs=10000001\n");
    assert(!memcmp(pins_before, f.pins, sizeof(pins_before)));
    assert(!c.armed && !c.moving && !c.magnet);
    assert(!c.board_ready); /* No frame/debounce needed for live electrical inputs. */
}
static void arm(ScbCore *c) { cmd(c, "PING\nARM\nSET_STEPS 3\nORIGIN a1\n", 1000); assert(c->armed && c->origin_valid); }
static void test_motion(void) {
    ScbCore c; Fake f; init(&c, &f);
    cmd(&c, "@1 MOVE a1 b1\n", 10); contains(&f, "ERR 1 NOT_ARMED\n");
    arm(&c); cmd(&c, "@2 GOTO b1\n", 2000); ticks(&c, 2000, 45);
    assert(f.x_pulses == 3 && !f.y_pulses && c.x == 3);
    assert(!c.moving && f.pins[SCB_PIN_MOTOR_EN]); contains(&f, "DONE 2 MOTION\n");
    cmd(&c, "@3 MOVE a1 a2\n", 49000); contains(&f, "ERR 3 SOURCE_NOT_ALIGNED\n");
    cmd(&c, "@4 MOVE b1 b2\n", 50000); assert(c.magnet && !f.pins[SCB_PIN_MOTOR_EN]);
    ticks(&c, 50000, 150); assert(f.y_pulses == 3 && !c.moving && !c.magnet);
    contains(&f, "DONE 4 MOTION\n");
    cmd(&c, "HOME\n", 201000); contains(&f, "NO_HOME_SWITCHES");
    cmd(&c, "@5 GOTO h8\n@6 STOP\n", 202000);
    assert(!c.armed && !c.moving && !c.origin_valid && !c.magnet && f.pins[SCB_PIN_MOTOR_EN]);
    contains(&f, "ERR 5 STOPPED\n"); contains(&f, "ACK 6 STOP\n");
}
static void test_watchdogs(void) {
    ScbCore c; Fake f; init(&c, &f); arm(&c);
    cmd(&c, "@21 MOVE a1 h8\n", 2000);
    /* Late PING does not rescue stale armed/motion state. */
    cmd(&c, "@22 PING\n", 3000000);
    assert(!c.armed && !c.moving && !c.magnet && f.pins[SCB_PIN_MOTOR_EN]);
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
    assert(!c.moving && !c.armed && f.pins[SCB_PIN_MOTOR_EN]); contains(&f, "FAULT GPIO\n");
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
static void test_spec_timing_and_power_defaults(void) {
    ScbCore c; Fake f; init(&c, &f);
    /* 1 ms control schedule: full frames arrive at 8, 18, 28 ... ms. */
    ticks(&c, 1, 1000);
    assert(c.scan_frames == 100 && c.frame_us == 10000 && c.max_frame_us == 10000);
    assert(c.scan_misses == 0 && c.debounce_us == 10000);
    f.board[12] = true;
    ticks(&c, 1000001, 30);
    assert(c.stable[12] && c.debounce_us == 10000);
    cmd(&c, "@31 TIMING\n", 1030002);
    contains(&f, "TIMING 31 frames=103 frame_us=10000 max_us=10000 misses=0 debounce_us=10000\n");
    cmd(&c, "LED a1 255 100 40\n", 1030003);
    assert(c.leds.pixels[0].red == SCB_LED_CHANNEL_LIMIT);
    assert(c.leds.pixels[0].green == SCB_LED_CHANNEL_LIMIT);
    assert(c.leds.pixels[0].blue == SCB_LED_CHANNEL_LIMIT);
    cmd(&c, "@32 PLATFORM\n", 1030004); contains(&f, "ERR 32 UNAVAILABLE\n");
    /* A delayed schedule must be measured, not reported as the target rate. */
    ticks(&c, 1100001, 30);
    assert(c.scan_misses > 0 && c.max_frame_us >= SCB_SCAN_LIMIT_US);
    /* Sensor/LED traffic while moving still advances complete scan frames. */
    init(&c, &f); arm(&c);
    cmd(&c, "GOTO h8\n", 2000);
    for (int i = 1; i <= 200; ++i) {
        if (i % 5 == 0) cmd(&c, "LED a1 10 0 0\n", 2000 + i * 1000);
        scb_core_tick(&c, 2000 + i * 1000);
    }
    assert(c.scan_frames >= 19 && c.scan_misses == 0);
    const unsigned pins[] = {SCB_PIN_LED, SCB_PIN_ROW_A0, SCB_PIN_ROW_A1, SCB_PIN_ROW_A2,
        1,2,3,4,5,6,7,8,SCB_PIN_UART_TX,SCB_PIN_UART_RX,SCB_PIN_MAGNET,
        SCB_PIN_X_STEP,SCB_PIN_X_DIR,SCB_PIN_Y_STEP,SCB_PIN_Y_DIR,SCB_PIN_MOTOR_EN};
    assert(sizeof(pins) / sizeof(pins[0]) == 20);
    const unsigned columns[] = SCB_COLUMN_PINS;
    /* Cross-check the actual scan input list, not just an independent whitelist. */
    for (unsigned i = 0; i < 8; ++i) assert(pins[4 + i] == columns[i]);
    assert(SCB_PIN_UART_TX == 43 && SCB_PIN_UART_RX == 44);
    const unsigned exposed[] = {0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,
        18,19,20,21,26,33,34,35,36,37,38,39,40,41,42,43,44,45,46};
    for (unsigned i = 0; i < 20; ++i) {
        assert(pins[i] < SCB_GPIO_COUNT);
        assert(!(pins[i] >= 22 && pins[i] <= 32)); /* Missing GPIOs / module memory. */
        assert(pins[i] != 0 && pins[i] != 45 && pins[i] != 46); /* Boot straps. */
        assert(pins[i] != 18); /* Board RGB LED. */
        assert(pins[i] != 19 && pins[i] != 20); /* Keep native USB available. */
        bool found = false;
        for (unsigned j = 0; j < sizeof(exposed)/sizeof(exposed[0]); ++j)
            if (pins[i] == exposed[j]) found = true;
        assert(found);
    }
    const unsigned outputs[] = {SCB_PIN_LED, SCB_PIN_ROW_A0, SCB_PIN_ROW_A1,
        SCB_PIN_ROW_A2, SCB_PIN_MAGNET, SCB_PIN_X_STEP, SCB_PIN_X_DIR,
        SCB_PIN_Y_STEP, SCB_PIN_Y_DIR, SCB_PIN_MOTOR_EN};
    for (unsigned i = 0; i < sizeof(outputs)/sizeof(outputs[0]); ++i) {
        assert(outputs[i] != 46); /* S2 GPIO46 is input-only. */
        assert(outputs[i] != SCB_PIN_UART_TX && outputs[i] != SCB_PIN_UART_RX);
    }
    for (unsigned i = 0; i < 20; ++i)
        for (unsigned j = i + 1; j < 20; ++j) assert(pins[i] != pins[j]);
}
int main(void) {
    test_board(); test_scan_covers_all_64_squares();
    test_sensor_traces_use_the_accepted_frame();
    test_protocol(); test_live_inputs_do_not_drive_sensor_outputs();
    test_motion(); test_watchdogs(); test_ambiguous_and_led_mapping();
    test_spec_timing_and_power_defaults();
    puts("ESP32-S2 portable-core tests passed (simulated GPIO): sensing, framing, outputs, motion, watchdogs.");
}
