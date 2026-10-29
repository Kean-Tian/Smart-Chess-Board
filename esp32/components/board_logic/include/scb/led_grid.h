#ifndef SCB_LED_GRID_H
#define SCB_LED_GRID_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define SCB_LED_COUNT 64U

typedef struct {
    uint8_t red;
    uint8_t green;
    uint8_t blue;
} ScbRgb;

typedef struct {
    ScbRgb pixels[SCB_LED_COUNT];
    bool serpentine;
    bool first_row_is_rank_eight;
    bool first_column_is_file_h;
} ScbLedGrid;

void scb_led_grid_init(ScbLedGrid *grid);
int scb_led_index(const ScbLedGrid *grid, unsigned int square);
int scb_led_set_square(ScbLedGrid *grid, unsigned int square, ScbRgb color);
void scb_led_clear(ScbLedGrid *grid);
int scb_led_mark_move(ScbLedGrid *grid, unsigned int from,
                      unsigned int to, bool legal);

#endif
