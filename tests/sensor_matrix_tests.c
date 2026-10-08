#include "scb/sensor_matrix.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    bool levels[54];
    bool rows[SCB_BOARD_ROWS][SCB_BOARD_COLUMNS];
    unsigned int sleep_calls;
    unsigned int read_rows[SCB_BOARD_ROWS];
    unsigned int read_count;
    unsigned int writes_to_unwired_gpio;
} FakeGpio;

static void require(bool condition, const char *message) {
    if (!condition) {
        fprintf(stderr, "FAIL: %s\n", message);
        exit(1);
    }
}

static int fake_write(void *context, unsigned int pin, bool high) {
    FakeGpio *gpio = context;
    if (pin >= 54U) return -1;
    if (pin != 17U && pin != 27U && pin != 22U) {
        ++gpio->writes_to_unwired_gpio;
    }
    gpio->levels[pin] = high;
    return 0;
}

static int fake_read(void *context,
                     const unsigned int pins[SCB_BOARD_COLUMNS],
                     bool values[SCB_BOARD_COLUMNS]) {
    FakeGpio *gpio = context;
    unsigned int row = (gpio->levels[17] ? 1U : 0U) |
                       (gpio->levels[27] ? 2U : 0U) |
                       (gpio->levels[22] ? 4U : 0U);
    if (gpio->read_count >= SCB_BOARD_ROWS) return -1;
    gpio->read_rows[gpio->read_count++] = row;
    for (size_t column = 0U; column < SCB_BOARD_COLUMNS; ++column) {
        require(pins[column] ==
                    (unsigned int[]){5U, 6U, 12U, 13U, 16U, 19U, 20U, 21U}[column],
                "column pin order");
        values[column] = gpio->rows[row][column];
    }
    return 0;
}

static void fake_sleep(void *context, unsigned int microseconds) {
    FakeGpio *gpio = context;
    (void)microseconds;
    ++gpio->sleep_calls;
}

static ScbSensorMatrix make_matrix(FakeGpio *gpio) {
    ScbGpioOps ops = {gpio, fake_write, fake_read, fake_sleep};
    ScbSensorMatrix matrix;
    scb_sensor_matrix_defaults(&matrix, ops);
    return matrix;
}

static void make_snapshot(bool output[SCB_BOARD_SQUARES],
                          const char *first, const char *second) {
    memset(output, 0, sizeof(bool) * SCB_BOARD_SQUARES);
    if (first != NULL) output[scb_square_index(first)] = true;
    if (second != NULL) output[scb_square_index(second)] = true;
}

static void test_matrix_scan_and_mapping(void) {
    FakeGpio gpio = {0};
    ScbSensorMatrix matrix = make_matrix(&gpio);
    bool occupied[SCB_BOARD_SQUARES];
    gpio.rows[0][0] = true;
    gpio.rows[0][3] = true;
    gpio.rows[7][7] = true;
    require(scb_sensor_matrix_initialize(&matrix) == 0, "initialize matrix");
    require(scb_sensor_matrix_scan(&matrix, occupied) == 0, "scan matrix");
    require(occupied[scb_square_index("a1")], "map a1");
    require(occupied[scb_square_index("d1")], "detect a second column in the same row");
    require(occupied[scb_square_index("h8")], "map h8");
    require(gpio.sleep_calls == 16U, "two delays per row");
    require(gpio.read_count == SCB_BOARD_ROWS, "read all eight rows");
    for (unsigned int row = 0U; row < SCB_BOARD_ROWS; ++row) {
        require(gpio.read_rows[row] == row, "74HC138 address sequence");
    }
    require(gpio.writes_to_unwired_gpio == 0U, "write only A0, A1, and A2");
}

static void test_active_low_inputs(void) {
    FakeGpio gpio = {0};
    ScbSensorMatrix matrix = make_matrix(&gpio);
    bool occupied[SCB_BOARD_SQUARES];
    for (size_t row = 0U; row < SCB_BOARD_ROWS; ++row) {
        for (size_t column = 0U; column < SCB_BOARD_COLUMNS; ++column) {
            gpio.rows[row][column] = true;
        }
    }
    gpio.rows[0][0] = false;
    matrix.columns_active_low = true;
    require(scb_sensor_matrix_scan(&matrix, occupied) == 0, "active-low scan");
    require(occupied[scb_square_index("a1")], "active-low a1");
    unsigned int count = 0U;
    for (size_t index = 0U; index < SCB_BOARD_SQUARES; ++index) {
        if (occupied[index]) ++count;
    }
    require(count == 1U, "only one active-low square");
}

static void test_debouncer(void) {
    ScbDebouncer debouncer;
    bool empty[SCB_BOARD_SQUARES] = {0};
    bool changed[SCB_BOARD_SQUARES] = {0};
    bool stable[SCB_BOARD_SQUARES];
    changed[0] = true;
    require(scb_debouncer_initialize(&debouncer, 3U) == 0, "initialize debounce");
    require(scb_debouncer_update(&debouncer, empty, stable) == 0, "empty read 1");
    require(scb_debouncer_update(&debouncer, empty, stable) == 0, "empty read 2");
    require(scb_debouncer_update(&debouncer, empty, stable) == 1, "empty stable");
    require(scb_debouncer_update(&debouncer, changed, stable) == 0, "changed read 1");
    require(scb_debouncer_update(&debouncer, changed, stable) == 0, "changed read 2");
    require(scb_debouncer_update(&debouncer, changed, stable) == 1, "changed stable");
    require(stable[0], "publish changed square");
}

static void test_lift_return_and_move(void) {
    ScbMoveTracker tracker;
    ScbBoardEvent event;
    bool board[SCB_BOARD_SQUARES];
    scb_move_tracker_initialize(&tracker);
    make_snapshot(board, "e2", NULL);
    require(scb_move_tracker_process(&tracker, board, &event) == 0, "initial state");
    make_snapshot(board, NULL, NULL);
    require(scb_move_tracker_process(&tracker, board, &event) == 0, "lift state");
    require(event.kind == SCB_EVENT_LIFT && strcmp(event.message, "LIFT e2") == 0,
            "detect lift");
    make_snapshot(board, "e2", NULL);
    require(scb_move_tracker_process(&tracker, board, &event) == 0, "return state");
    require(event.kind == SCB_EVENT_PLACE && strcmp(event.message, "RETURN e2") == 0,
            "detect return");
    make_snapshot(board, NULL, NULL);
    (void)scb_move_tracker_process(&tracker, board, &event);
    make_snapshot(board, "e4", NULL);
    require(scb_move_tracker_process(&tracker, board, &event) == 0, "move state");
    require(event.kind == SCB_EVENT_MOVE && strcmp(event.message, "MOVE e2e4") == 0,
            "detect normal move");
}

static void test_capture(void) {
    ScbMoveTracker tracker;
    ScbBoardEvent event;
    bool board[SCB_BOARD_SQUARES];
    scb_move_tracker_initialize(&tracker);
    make_snapshot(board, "e4", "d5");
    (void)scb_move_tracker_process(&tracker, board, &event);
    make_snapshot(board, "e4", NULL);
    (void)scb_move_tracker_process(&tracker, board, &event);
    make_snapshot(board, NULL, NULL);
    (void)scb_move_tracker_process(&tracker, board, &event);
    make_snapshot(board, "d5", NULL);
    require(scb_move_tracker_process(&tracker, board, &event) == 0, "capture state");
    require(event.kind == SCB_EVENT_MOVE && strcmp(event.message, "MOVE e4d5") == 0,
            "detect capture");
}

static void test_invalid_overlapping_pins(void) {
    FakeGpio gpio = {0};
    ScbSensorMatrix matrix = make_matrix(&gpio);
    matrix.column_pins[0] = matrix.address_pins[0];
    require(scb_sensor_matrix_validate(&matrix) < 0, "reject overlapping GPIO pins");
}

int main(void) {
    test_matrix_scan_and_mapping();
    test_active_low_inputs();
    test_debouncer();
    test_lift_return_and_move();
    test_capture();
    test_invalid_overlapping_pins();
    puts("All sensor-matrix C tests passed.");
    return 0;
}
