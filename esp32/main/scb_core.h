#ifndef SCB_CORE_H
#define SCB_CORE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "scb/sensor_matrix.h"
#include "scb/led_grid.h"

#define SCB_LINE_CAPACITY 128U
typedef struct {
    void *ctx;
    bool (*write)(void *, unsigned pin, bool high);
    bool (*read)(void *, unsigned pin);
    bool (*pulse)(void *, unsigned pin); /* One HIGH/LOW pulse, >=5 us HIGH. */
    bool (*show_leds)(void *, const ScbLedGrid *);
    void (*emit)(void *, const char *line); /* Whole newline-terminated frames. */
} ScbIo;

typedef struct {
    ScbIo io;
    ScbDebouncer debounce;
    ScbMoveTracker tracker;
    ScbLedGrid leds;
    bool sampled[64], raw_frame[64], stable[64], board_ready, active_low;
    unsigned row;
    int64_t row_ready_at;
    bool armed, moving, magnet, origin_valid, magnet_wanted;
    unsigned steps_per_tile, move_id, ignore_frames;
    int x, y, target_x, target_y;
    int64_t last_ping, next_step_at, move_started, magnet_started;
    char input[SCB_LINE_CAPACITY];
    size_t input_len;
    bool discard_line;
} ScbCore;

bool scb_core_init(ScbCore *, ScbIo, int64_t now_us);
void scb_core_tick(ScbCore *, int64_t now_us);
void scb_core_feed(ScbCore *, const void *, size_t, int64_t now_us);
/* For platform-level failures, also invalidates the carriage reference. */
void scb_core_fault(ScbCore *, const char *reason);
#endif
