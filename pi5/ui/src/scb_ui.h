#ifndef SCB_TOUCH_UI_H
#define SCB_TOUCH_UI_H
#include "lvgl.h"
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#define SCB_UI_WIDTH 720
#define SCB_UI_HEIGHT 1280
typedef enum {
    UI_HOME, UI_SETUP, UI_PROFILES, UI_HISTORY, UI_DIAGNOSTICS,
    UI_PLAYER_EDITOR, UI_BOARD_SETUP, UI_GAME, UI_REVIEW, UI_MOVE_EDITOR, UI_SCREEN_COUNT
} UiScreen;

void scb_ui_init(const char *database_path);
void scb_ui_shutdown(void);
void scb_ui_show(UiScreen screen);
void scb_ui_text_input(const char *value);
void scb_ui_backspace(void);
void scb_ui_submit(void);
void scb_ui_tick(void);
void scb_ui_write_hotspots(FILE *output);
bool scb_ui_smoke_test(void);
bool scb_ui_service_test(void);
const char *scb_ui_screen_name(UiScreen screen);
#endif
