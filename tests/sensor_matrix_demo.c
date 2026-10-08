#include "scb/sensor_matrix.h"

#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    bool levels[54];
    bool rows[SCB_BOARD_ROWS][SCB_BOARD_COLUMNS];
    bool show_rows;
} DemoGpio;

typedef struct {
    DemoGpio gpio;
    ScbSensorMatrix matrix;
    ScbDebouncer debouncer;
    ScbMoveTracker tracker;
    bool raw[SCB_BOARD_SQUARES];
    bool stable[SCB_BOARD_SQUARES];
} Demo;

static void fail(const char *message) {
    fprintf(stderr, "Demo failed: %s\n", message);
    exit(EXIT_FAILURE);
}

static int demo_write(void *context, unsigned int pin, bool high) {
    DemoGpio *gpio = context;
    if (pin != 17U && pin != 27U && pin != 22U) return -1;
    gpio->levels[pin] = high;
    return 0;
}

static int demo_read_columns(void *context,
                             const unsigned int pins[SCB_BOARD_COLUMNS],
                             bool values[SCB_BOARD_COLUMNS]) {
    DemoGpio *gpio = context;
    unsigned int row = (gpio->levels[17] ? 1U : 0U) |
                       (gpio->levels[27] ? 2U : 0U) |
                       (gpio->levels[22] ? 4U : 0U);

    for (unsigned int column = 0U; column < SCB_BOARD_COLUMNS; ++column) {
        if (pins[column] !=
            (unsigned int[]){5U, 6U, 12U, 13U, 16U, 19U, 20U, 21U}[column]) {
            return -1;
        }
        values[column] = gpio->rows[row][column];
    }

    if (gpio->show_rows) {
        printf("  A2A1A0=%u%u%u -> Y%u; columns a-h=",
               gpio->levels[22] ? 1U : 0U,
               gpio->levels[27] ? 1U : 0U,
               gpio->levels[17] ? 1U : 0U, row);
        for (unsigned int column = 0U; column < SCB_BOARD_COLUMNS; ++column) {
            putchar(values[column] ? '1' : '0');
        }
        putchar('\n');
        if (row == SCB_BOARD_ROWS - 1U) gpio->show_rows = false;
    }
    return 0;
}

static void demo_sleep(void *context, unsigned int microseconds) {
    (void)context;
    (void)microseconds;
}

static void demo_initialize(Demo *demo) {
    ScbGpioOps ops = {&demo->gpio, demo_write, demo_read_columns, demo_sleep};
    memset(demo, 0, sizeof(*demo));
    scb_sensor_matrix_defaults(&demo->matrix, ops);
    if (scb_sensor_matrix_initialize(&demo->matrix) < 0 ||
        scb_debouncer_initialize(&demo->debouncer, 3U) < 0) {
        fail("initialization");
    }
    scb_move_tracker_initialize(&demo->tracker);
}

static void set_square(Demo *demo, const char *name, bool occupied) {
    int index = scb_square_index(name);
    if (index < 0) fail("invalid square name");
    demo->gpio.rows[(unsigned int)index / SCB_BOARD_COLUMNS]
                   [(unsigned int)index % SCB_BOARD_COLUMNS] = occupied;
}

static void scan_once(Demo *demo, bool expect_event) {
    int result;
    if (scb_sensor_matrix_scan(&demo->matrix, demo->raw) < 0) {
        fail("matrix scan");
    }
    result = scb_debouncer_update(&demo->debouncer, demo->raw, demo->stable);
    if (result < 0) fail("debouncing");
    if (result == 0) {
        if (expect_event) fail("expected a stable board event");
        puts("  Reading held for debounce; no event yet.");
        return;
    }
    if (!expect_event) fail("unexpected board event");

    ScbBoardEvent event;
    if (scb_move_tracker_process(&demo->tracker, demo->stable, &event) < 0) {
        fail("move tracking");
    }
    printf("  Terminal event: %s\n", event.message);
}

static void stable_step(Demo *demo, const char *label) {
    printf("\n%s\n", label);
    scan_once(demo, false);
    scan_once(demo, false);
    scan_once(demo, true);
}

int main(void) {
    Demo demo;

    puts("SIMULATED GPIO DEMO - no Raspberry Pi or sensor board is used");
    demo_initialize(&demo);
    demo.gpio.show_rows = true;
    stable_step(&demo, "1. Empty board: cycle all 74HC138 addresses");
    set_square(&demo, "a1", true);
    set_square(&demo, "d1", true);
    demo.gpio.show_rows = true;
    stable_step(&demo, "2. Two occupied columns in the same row");

    demo_initialize(&demo);
    stable_step(&demo, "3. Empty board baseline");
    set_square(&demo, "a1", true);
    puts("\n4. One noisy reading at a1");
    scan_once(&demo, false);
    set_square(&demo, "a1", false);
    scan_once(&demo, false);
    puts("  Noise ignored: the board returned to its previous stable state.");

    demo_initialize(&demo);
    set_square(&demo, "e2", true);
    stable_step(&demo, "5. Establish baseline with a piece on e2");
    set_square(&demo, "e2", false);
    stable_step(&demo, "6. Lift the piece from e2");
    set_square(&demo, "e2", true);
    stable_step(&demo, "7. Return the piece to e2");
    set_square(&demo, "e2", false);
    stable_step(&demo, "8. Lift the piece again");
    set_square(&demo, "e4", true);
    stable_step(&demo, "9. Place it on e4: normal move");

    demo_initialize(&demo);
    set_square(&demo, "e4", true);
    set_square(&demo, "d5", true);
    stable_step(&demo, "10. Establish capture baseline: e4 and d5 occupied");
    set_square(&demo, "d5", false);
    stable_step(&demo, "11. Remove the piece from d5");
    set_square(&demo, "e4", false);
    stable_step(&demo, "12. Lift the piece from e4");
    set_square(&demo, "d5", true);
    stable_step(&demo, "13. Place it on d5: capture");

    puts("\nEnd of simulated demonstration.");
    return EXIT_SUCCESS;
}
