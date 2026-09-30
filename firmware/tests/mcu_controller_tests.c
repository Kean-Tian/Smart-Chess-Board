#include "../include/scb/mcu_controller.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    bool button;
    bool halls[SCB_BOARD_SQUARE_COUNT];
    char messages[8][32];
    int message_count;
    bool led;
} FakeBoard;

static bool read_button(void *context) { return ((FakeBoard *)context)->button; }
static bool read_hall(void *context, uint8_t square) { return ((FakeBoard *)context)->halls[square]; }
static void write_led(void *context, bool on) { ((FakeBoard *)context)->led = on; }

static void send_line(void *context, const char *line) {
    FakeBoard *board = (FakeBoard *)context;
    if (board->message_count < 8) {
        (void)snprintf(board->messages[board->message_count], sizeof(board->messages[0]), "%s", line);
        ++board->message_count;
    }
}

static void require(bool condition, const char *message) {
    if (!condition) {
        fprintf(stderr, "FAIL: %s\n", message);
        exit(1);
    }
}

static bool contains(const FakeBoard *board, const char *expected) {
    for (int index = 0; index < board->message_count; ++index) {
        if (strcmp(board->messages[index], expected) == 0) return true;
    }
    return false;
}

static ScbPlatform fake_platform(FakeBoard *board) {
    ScbPlatform platform = {board, read_button, read_hall, write_led, send_line};
    return platform;
}

int main(void) {
    FakeBoard board = {0};
    board.halls[12] = true;
    ScbMcuController controller;
    scb_mcu_init(&controller, fake_platform(&board), false);
    for (uint32_t time = 0; time <= 30; time += 5) scb_mcu_loop(&controller, time);
    require(scb_mcu_sensor_occupied(&controller, 12), "debounce initial Hall sensor state");
    require(board.message_count == 0, "do not report initial calibration as a move");

    board.halls[12] = false;
    for (uint32_t time = 40; time <= 70; time += 5) scb_mcu_loop(&controller, time);
    require(board.led, "light status LED while piece is lifted");
    board.halls[28] = true;
    for (uint32_t time = 80; time <= 110; time += 5) scb_mcu_loop(&controller, time);
    require(contains(&board, "SCB1 SENSOR e2 0"), "report debounced Hall change over UART");
    require(contains(&board, "SCB1 MOVE e2 e4"), "report completed physical move over UART");
    require(!board.led, "turn off status LED after move completion");

    FakeBoard button_board = {0};
    ScbMcuController button_controller;
    scb_mcu_init(&button_controller, fake_platform(&button_board), true);
    for (uint32_t time = 0; time <= 30; time += 5) scb_mcu_loop(&button_controller, time);
    button_board.button = true;
    for (uint32_t time = 35; time <= 70; time += 5) scb_mcu_loop(&button_controller, time);
    button_board.button = false;
    for (uint32_t time = 75; time <= 105; time += 5) scb_mcu_loop(&button_controller, time);
    button_board.button = true;
    for (uint32_t time = 110; time <= 145; time += 5) scb_mcu_loop(&button_controller, time);
    for (uint32_t time = 150; time <= 180; time += 5) scb_mcu_loop(&button_controller, time);
    require(contains(&button_board, "SCB1 SENSOR e2 0"), "button mode simulates lifting e2");
    require(contains(&button_board, "SCB1 SENSOR e3 1"), "button mode simulates placing on e3");
    require(contains(&button_board, "SCB1 MOVE e2 e3"), "button mode exercises complete move state machine");
    puts("All MCU controller tests passed.");
    return 0;
}
