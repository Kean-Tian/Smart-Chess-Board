#include "scb/led_grid.h"

#include <errno.h>
#include <string.h>

void scb_led_grid_init(ScbLedGrid *grid) {
    if (grid == NULL) return;
    memset(grid, 0, sizeof(*grid));
    grid->serpentine = true;
}

int scb_led_index(const ScbLedGrid *grid, unsigned int square) {
    if (grid == NULL || square >= SCB_LED_COUNT) {
        errno = EINVAL;
        return -1;
    }
    unsigned int row = square / 8U;
    unsigned int column = square % 8U;
    if (grid->first_row_is_rank_eight) row = 7U - row;
    if (grid->first_column_is_file_h) column = 7U - column;
    if (grid->serpentine && (row & 1U)) column = 7U - column;
    return (int)(row * 8U + column);
}

int scb_led_set_square(ScbLedGrid *grid, unsigned int square, ScbRgb color) {
    int led = scb_led_index(grid, square);
    if (led < 0) return -1;
    grid->pixels[led] = color;
    return 0;
}

void scb_led_clear(ScbLedGrid *grid) {
    if (grid != NULL) memset(grid->pixels, 0, sizeof(grid->pixels));
}

int scb_led_mark_move(ScbLedGrid *grid, unsigned int from,
                      unsigned int to, bool legal) {
    const ScbRgb green = {0U, 20U, 0U};
    const ScbRgb blue = {0U, 0U, 20U};
    const ScbRgb red = {20U, 0U, 0U};
    if (grid == NULL || from >= 64U || to >= 64U) {
        errno = EINVAL;
        return -1;
    }
    scb_led_clear(grid);
    if (scb_led_set_square(grid, from, legal ? blue : red) < 0) return -1;
    return scb_led_set_square(grid, to, legal ? green : red);
}

