/* Native Pi UI: real players, local service events, physical games and saved review. */
#include "scb_ui.h"
#include "player_store.h"
#include "ui_bridge.h"
#include <inttypes.h>
#include <stdarg.h>
#include <time.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BG 0xF8F7F3
#define PAPER 0xFFFFFF
#define INK 0x20231F
#define MUTED 0x666A60
#define GOLD 0xCEB888
#define SOFT 0xEEE8DB
#define RED 0xA94337

typedef enum {
    A_NONE, A_NAV, A_SELECT, A_NEW, A_EDIT, A_SAVE, A_CANCEL, A_DELETE,
    A_CONFIRM_DELETE, A_PAGE, A_RETRY, A_MODE, A_SIDE, A_CLOCK, A_PICK,
    A_USE_PLAYER, A_PREPARE, A_CHECK, A_VERIFIED, A_START, A_PAUSE, A_END,
    A_CONFIRM_END, A_HINT, A_CONFIRM_MOVE, A_PROMOTE, A_CONNECT,
    A_HISTORY_PAGE, A_REVIEW, A_REVIEW_STEP, A_GUIDANCE, A_SCAN, A_SQUARE, A_CONFIRM_COMPUTER, A_COACH, A_COACH_RETRY,
    A_RESET_FAULT, A_EXECUTE_COMPUTER
} Action;
typedef struct {
    lv_obj_t *obj;
    const char *id, *target;
    Action action;
    int64_t value;
} Hit;
static Hit hits[128];
static unsigned hit_count;
static UiScreen current;
static PlayerStore store;
static ScbPlayer rows[SCB_PLAYER_PAGE_SIZE], selected;
static int row_count, player_count, page_offset;
static bool data_ok;
static int64_t editing_id, deleting_id;
static lv_obj_t *name_input, *form_error;
static char database_path[4096];
static const char *screen_names[] = {"home", "setup", "profiles", "history", "player-editor", "board-setup", "game", "review", "move-editor", "diagnostics", "instructions", "coaching"};
static const char *mode_codes[] = {"pvp", "pvc", "coach"};
static const char *mode_titles[] = {"Two players", "Vs computer", "With coaching"};
static UiBridge bridge;
static struct {
    /* 界面中的临时选择；真正的对局状态由 Python 后台确认。 */
    int mode, human, minutes, pick_side, port_index, history_offset, review_return;
    ScbPlayer white, black;
    bool verified, show_hint, ending, review_pending, reconnecting, guidance;
    int selected_square, coach[2];
    int64_t review_id, review_ply, review_total;
    char instruction_move[8];
} config;
static lv_obj_t *title_label, *status_label, *clock_labels[2], *last_move_label;
static lv_obj_t *pause_button, *hint_button, *end_button, *move_button;
static lv_obj_t *check_button, *start_button, *verified_button, *connection_button;
static lv_obj_t *port_dropdown;
static lv_obj_t *review_count, *review_move, *review_previous, *review_next, *continue_button;
static lv_obj_t *piece_images[64], *sensor_tiles[64];
static lv_obj_t *coaching_buttons[2], *coaching_text, *coaching_retry;
static lv_obj_t *guidance_button, *scan_button, *sensor_detail, *sensor_timing, *computer_confirm;
static lv_obj_t *fault_reset_button, *automatic_button;
static char local_notice[256], port_options[1600];
static unsigned last_changes;
static uint32_t last_live_refresh;
static bool end_dialog_open;
static bool service_online(void);
static bool state_flag(const char *path);
static void refresh_live(void);
static void request_history(void);
static void draw_position(int x, int y, int size, const char *fen);
static bool command(const char *format, ...);

static const lv_font_t *font(int size) {
    switch(size) {
        case 20: return &lv_font_montserrat_20;
        case 28: return &lv_font_montserrat_28;
        case 32: return &lv_font_montserrat_32;
        case 40: return &lv_font_montserrat_40;
        default: return &lv_font_montserrat_24;
    }
}
static lv_obj_t *root(void) { return lv_screen_active(); }
static lv_obj_t *box(lv_obj_t *parent, int x, int y, int w, int h, uint32_t fill, int radius) {
    /* 卡片的公共样式；坐标相对于 parent，而不是始终相对于屏幕。 */
    lv_obj_t *o = lv_obj_create(parent);
    lv_obj_remove_style_all(o);
    lv_obj_set_pos(o, x, y);
    lv_obj_set_size(o, w, h);
    lv_obj_set_style_bg_color(o, lv_color_hex(fill), 0);
    lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(o, radius, 0);
    lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
    return o;
}
static lv_obj_t *text(lv_obj_t *parent, const char *value, int x, int y, int w, int size, uint32_t color) {
    /* 创建文字控件，统一字体、颜色和自动换行。 */
    lv_obj_t *o = lv_label_create(parent);
    lv_obj_set_pos(o, x, y);
    lv_obj_set_width(o, w);
    lv_obj_set_style_text_font(o, font(size), 0);
    lv_obj_set_style_text_color(o, lv_color_hex(color), 0);
    lv_obj_set_style_text_line_space(o, 5, 0);
    lv_label_set_long_mode(o, LV_LABEL_LONG_WRAP);
    lv_label_set_text(o, value);
    return o;
}
static void clipped_text(lv_obj_t *parent, const char *value, int x, int y, int w, int size, uint32_t color) {
    lv_obj_t *label = text(parent, value, x, y, w, size, color);
    lv_label_set_long_mode(label, LV_LABEL_LONG_DOT);
    lv_obj_set_height(label, 40);
}
static void click(lv_event_t *event);
static void editor_event(lv_event_t *event);
static lv_obj_t *button(lv_obj_t *parent, const char *title, int x, int y, int w, int h,
                        bool primary, const char *id, Action action, int64_t value, const char *target) {
    /* 创建按钮并绑定动作；真正点击后统一进入 click()。 */
    lv_obj_t *b = lv_button_create(parent);
    lv_obj_remove_style_all(b);
    lv_obj_set_pos(b, x, y);
    lv_obj_set_size(b, w, h);
    lv_obj_set_style_radius(b, 20, 0);
    lv_obj_set_style_bg_color(b, lv_color_hex(primary ? INK : SOFT), 0);
    lv_obj_set_style_bg_opa(b, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(b, lv_color_hex(primary ? 0x3A4035 : 0xDDD3BF), LV_STATE_PRESSED);
    lv_obj_set_style_bg_color(b, lv_color_hex(0xE6E5DF), LV_STATE_DISABLED);
    lv_obj_set_style_text_color(b, lv_color_hex(primary ? PAPER : INK), 0);
    lv_obj_set_style_text_color(b, lv_color_hex(0x92978C), LV_STATE_DISABLED);
    lv_obj_set_style_text_font(b, font(28), 0);
    lv_obj_t *label = lv_label_create(b);
    lv_label_set_text(label, title);
    lv_obj_set_width(label, w - 28);
    lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_center(label);
    if(hit_count >= sizeof(hits) / sizeof(hits[0])) abort();
    Hit *hit = &hits[hit_count++];
    *hit = (Hit){b, id, target, action, value};
    lv_obj_add_event_cb(b, click, LV_EVENT_CLICKED, hit);
    return b;
}
static void disable(lv_obj_t *o, bool condition) {
    if(condition) lv_obj_add_state(o, LV_STATE_DISABLED);
    else lv_obj_remove_state(o, LV_STATE_DISABLED);
}
static bool reload_players(void) {
    memset(&selected, 0, sizeof(selected));
    row_count = player_count = 0;
    data_ok = player_store_page(&store, page_offset, rows, &row_count, &player_count);
    if(data_ok && page_offset && page_offset >= player_count) {
        page_offset = player_count ? ((player_count - 1) / SCB_PLAYER_PAGE_SIZE) * SCB_PLAYER_PAGE_SIZE : 0;
        data_ok = player_store_page(&store, page_offset, rows, &row_count, &player_count);
    }
    if(data_ok) data_ok = player_store_selected(&store, &selected);
    return data_ok;
}
static void shell(const char *title, const char *subtitle) {
    /* 清理上一页控件并建立公共页头；后台的游戏状态不在这里删除。 */
    lv_obj_clean(root());
    hit_count = 0;
    name_input = form_error = NULL;
    title_label = status_label = last_move_label = NULL;
    clock_labels[0] = clock_labels[1] = NULL;
    pause_button = hint_button = end_button = move_button = NULL;
    check_button = start_button = verified_button = connection_button = NULL;
    port_dropdown = NULL;
    coaching_buttons[0] = coaching_buttons[1] = coaching_text = coaching_retry = NULL;
    guidance_button = scan_button = sensor_detail = sensor_timing = computer_confirm = NULL;
    fault_reset_button = automatic_button = NULL;
    memset(sensor_tiles, 0, sizeof(sensor_tiles));
    review_count = review_move = review_previous = review_next = continue_button = NULL;
    memset(piece_images, 0, sizeof(piece_images));
    end_dialog_open = false;
    lv_obj_set_style_bg_color(root(), lv_color_hex(BG), 0);
    lv_obj_set_style_text_color(root(), lv_color_hex(INK), 0);
    lv_obj_remove_flag(root(), LV_OBJ_FLAG_SCROLLABLE);
    if(current != UI_HOME) {
        /* 回放可能从不同页面进入，返回时使用记住的来源。 */
        UiScreen back = current == UI_PLAYER_EDITOR ? UI_PROFILES :
            current == UI_REVIEW ? (UiScreen)config.review_return : (current == UI_MOVE_EDITOR || current == UI_INSTRUCTIONS || current == UI_COACHING) ? UI_GAME :
            current == UI_BOARD_SETUP ? (config.reconnecting ? UI_GAME : UI_SETUP) : UI_HOME;
        button(root(), LV_SYMBOL_LEFT, 32, 88, 80, 80, false, "back", A_NAV, back, screen_names[back]);
    }
    title_label = text(root(), title, current == UI_HOME ? 32 : 136, 104, current == UI_HOME ? 656 : 552, 40, INK);
    text(root(), subtitle, 32, 190, 656, 24, MUTED);
}
static void feature(const char *title, const char *description, const char *symbol,
                    int x, int y, const char *id, UiScreen destination, bool primary) {
    bool has_page = destination < UI_SCREEN_COUNT;
    lv_obj_t *b = button(root(), "", x, y, 320, 244, primary, id,
                         has_page ? A_NAV : A_NONE, has_page ? destination : 0,
                         has_page ? screen_names[destination] : NULL);
    uint32_t color = primary ? PAPER : INK;
    text(b, symbol, 24, 26, 100, 40, primary ? GOLD : MUTED);
    text(b, title, 24, 104, 272, 32, color);
    if(description[0]) text(b, description, 24, 158, 272, 20, primary ? 0xDCDDD4 : MUTED);
}
static void home(void) {
    /* 主菜单四个入口，加上实际选中的玩家和当前游戏状态。 */
    reload_players();
    shell("Smart Chess Board", "Play, manage players and review your recorded games.");
    feature("New game", "Two players, computer\nor AI coaching", LV_SYMBOL_PLAY, 32, 280, "new-game", UI_SETUP, true);
    feature("Players", "Create, select and\nmanage saved players", LV_SYMBOL_DIRECTORY, 368, 280, "players", UI_PROFILES, false);
    feature("History", "Recorded results\nand move-by-move review", LV_SYMBOL_LIST, 32, 544, "history", UI_HISTORY, false);
    feature("Board test", "Live sensor occupancy\nand board connection", LV_SYMBOL_SETTINGS, 368, 544, "diagnostics", UI_DIAGNOSTICS, false);
    lv_obj_t *card = box(root(), 32, 836, 656, 144, PAPER, 24);
    text(card, "SELECTED PLAYER", 24, 22, 608, 20, MUTED);
    clipped_text(card, !data_ok ? "Database unavailable" : selected.id ? selected.name : "No player selected", 24, 68, 608, 32, INK);
    status_label = text(root(), "", 32, 1012, 656, 24, MUTED);
    lv_obj_set_height(status_label, 84);
    lv_label_set_long_mode(status_label, LV_LABEL_LONG_DOT);
    continue_button = button(root(), "Open current game", 32, 1120, 656, 88, false, "continue-game", A_NAV, UI_GAME, "game");
}
static void setup(void) {
    /* 读取玩家并显示模式、执棋颜色和时间；此时还没有正式开局。 */
    reload_players();
    if(config.white.id) player_store_get(&store, config.white.id, &config.white);
    if(config.black.id) player_store_get(&store, config.black.id, &config.black);
    if(config.mode != 1 && !config.white.id && selected.id) config.white = selected;
    if(config.mode == 1) {
        ScbPlayer *human = config.human ? &config.black : &config.white;
        if(!human->id && selected.id) *human = selected;
    }
    shell("New game", "Choose players, a game mode and time control.");
    text(root(), "GAME MODE", 32, 268, 656, 20, MUTED);
    const char *names[] = {"Two\nplayers", "Vs\ncomputer", "With\ncoaching"};
    for(int i = 0; i < 3; ++i)
        button(root(), names[i], 32+i*224, 310, 208, 110, config.mode == i,
               i == 0 ? "mode-pvp" : i == 1 ? "mode-computer" : "mode-coach", A_MODE, i, NULL);
    text(root(), "PLAYERS / TAP TO CHOOSE", 32, 460, 656, 20, MUTED);
    ScbPlayer *players[] = {&config.white, &config.black};
    for(int i = 0; i < 2; ++i) {
        bool computer = config.mode == 1 && i != config.human;
        lv_obj_t *b = button(root(), "", 32+i*336, 504, 320, 144, false,
                             i ? "choose-black" : "choose-white", A_PICK, i, "profiles");
        text(b, i ? "BLACK" : "WHITE", 24, 20, 272, 20, MUTED);
        clipped_text(b, computer ? "Stockfish" : players[i]->id ? players[i]->name : "Choose player", 24, 68, 272, 24, INK);
        disable(b, computer);
    }
    if(config.mode == 1) {
        text(root(), "YOUR SIDE", 32, 690, 656, 20, MUTED);
        button(root(), "White", 32, 736, 320, 80, !config.human, "side-white", A_SIDE, 0, NULL);
        button(root(), "Black", 368, 736, 320, 80, config.human != 0, "side-black", A_SIDE, 1, NULL);
    } else if(config.mode == 2) {
        text(root(), "AI COACHING / EACH PLAYER CHOOSES", 32, 678, 656, 20, MUTED);
        for(int i = 0; i < 2; ++i) {
            text(root(), i ? "Black" : "White", 32, 728+i*68, 140, 24, INK);
            button(root(), "ON", 200, 716+i*68, 224, 56, config.coach[i] == 1,
                   i ? "coach-black-on" : "coach-white-on", A_COACH, i*2+1, NULL);
            button(root(), "OFF", 440, 716+i*68, 248, 56, config.coach[i] == 0,
                   i ? "coach-black-off" : "coach-white-off", A_COACH, i*2, NULL);
        }
    } else {
        text(root(), "Two people playing on the physical board.", 32, 710, 656, 24, MUTED);
        text(root(), "Only legal, matching moves advance the game.", 32, 760, 656, 20, MUTED);
    }
    text(root(), "TIME CONTROL", 32, 860, 656, 20, MUTED);
    const int minutes[] = {5, 10, 0};
    const char *times[] = {"5 min", "10 min", "No clock"};
    for(int i = 0; i < 3; ++i)
        button(root(), times[i], 32+i*224, 904, 208, 88, config.minutes == minutes[i],
               i == 0 ? "clock-five" : i == 1 ? "clock-ten" : "clock-none", A_CLOCK, minutes[i], NULL);
    if(config.mode == 0)
        button(root(), config.guidance ? "Guidance: ON" : "Guidance: OFF", 32, 1010, 656, 64, false,
               "setup-guidance", A_GUIDANCE, 0, NULL);
    else if(config.mode == 2)
        text(root(), "Online AI advice is optional for each player.", 32, 1020, 656, 20, MUTED);
    status_label = text(root(), "", 32, 1084, 656, 20, RED);
    lv_obj_set_height(status_label, 36);
    lv_label_set_long_mode(status_label, LV_LABEL_LONG_DOT);
    button(root(), "Set up the board  " LV_SYMBOL_RIGHT, 32, 1128, 656, 96, true, "prepare", A_PREPARE, 0, "board-setup");
}
static void profiles(void) {
    /* 每次从数据库读取玩家；没有记录时显示空状态，不填入示例。 */
    reload_players();
    shell("Players", "Create and manage your saved player profiles.");
    char count[64];
    snprintf(count, sizeof(count), "%d saved player%s", player_count, player_count == 1 ? "" : "s");
    text(root(), data_ok ? count : "Player database unavailable", 32, 260, 656, 24, data_ok ? MUTED : RED);
    if(!data_ok || !player_count) {
        lv_obj_t *empty = box(root(), 32, 314, 656, 332, PAPER, 24);
        text(empty, data_ok ? "No players yet" : "Could not load players", 24, 32, 608, 32, INK);
        text(empty, data_ok ? "Create your first player below.\nNames are saved on this Pi." : store.error,
             24, 112, 608, 24, data_ok ? MUTED : RED);
    } else {
        for(int i = 0; i < row_count; ++i) {
            bool active = selected.id == rows[i].id;
            lv_obj_t *b = button(root(), "", 32, 314 + i * 114, 656, 100, active,
                                 "select-player", A_SELECT, rows[i].id, NULL);
            clipped_text(b, rows[i].name, 24, 14, 608, 28, active ? PAPER : INK);
            text(b, active ? "Selected" : "Tap to select", 24, 60, 608, 20, active ? 0xDCDDD4 : MUTED);
        }
    }
    disable(button(root(), LV_SYMBOL_LEFT, 32, 784, 120, 64, false, "previous-players", A_PAGE, -1, NULL), !data_ok || !page_offset);
    disable(button(root(), LV_SYMBOL_RIGHT, 568, 784, 120, 64, false, "next-players", A_PAGE, 1, NULL), !data_ok || page_offset + row_count >= player_count);
    char page[64];
    snprintf(page, sizeof(page), "Page %d / %d", page_offset / SCB_PLAYER_PAGE_SIZE + 1,
             player_count ? (player_count - 1) / SCB_PLAYER_PAGE_SIZE + 1 : 1);
    lv_obj_t *page_label = text(root(), data_ok ? page : "Unavailable", 178, 800, 364, 24, MUTED);
    lv_obj_set_style_text_align(page_label, LV_TEXT_ALIGN_CENTER, 0);
    char choice[80];
    snprintf(choice, sizeof(choice), "Selected: %s", selected.id ? selected.name : "None");
    ScbPlayerStats stats = {0};
    bool stats_ok = data_ok && selected.id && player_store_stats(&store, selected.id, &stats);
    if(stats_ok) snprintf(choice, sizeof(choice), "Completed: %d   W: %d   L: %d   Draw: %d", stats.completed, stats.wins, stats.losses, stats.draws);
    clipped_text(root(), !data_ok ? "Selection unavailable" : stats_ok ? choice : "Select a player to view game counts", 32, 850, 656, 20, MUTED);
    button(root(), data_ok ? "Create player" : "Retry database", 32, 892, 656, 84, true,
           data_ok ? "create-player" : "retry-database", data_ok ? A_NEW : A_RETRY, 0, "player-editor");
    disable(button(root(), "Rename", 32, 996, 320, 80, false, "rename-player", A_EDIT, 0, "player-editor"), !data_ok || !selected.id);
    disable(button(root(), "Delete", 368, 996, 320, 80, false, "delete-player", A_DELETE, selected.id, NULL), !data_ok || !selected.id);
    disable(button(root(), "Use selected player", 32, 1112, 656, 88, true, "use-player", A_USE_PLAYER, 0, "setup"), !data_ok || !selected.id);
}
static void player_editor(void) {
    /* 新建和改名共用输入页，将屏幕键盘绑定到名字输入框。 */
    shell(editing_id ? "Rename player" : "Create player", "Save a player name to your local database.");
    text(root(), "PLAYER NAME", 32, 272, 656, 20, MUTED);
    name_input = lv_textarea_create(root());
    lv_obj_set_pos(name_input, 32, 316);
    lv_obj_set_size(name_input, 656, 104);
    lv_obj_set_style_text_font(name_input, font(28), 0);
    lv_textarea_set_one_line(name_input, true);
    lv_obj_set_height(name_input, 104);
    lv_textarea_set_max_length(name_input, SCB_PLAYER_NAME_MAX);
    lv_textarea_set_placeholder_text(name_input, "Enter a name");
    lv_textarea_set_text(name_input, editing_id ? selected.name : "");
    lv_obj_add_event_cb(name_input, editor_event, LV_EVENT_READY, NULL);
    form_error = text(root(), "", 32, 448, 656, 24, RED);
    lv_obj_set_height(form_error, 88);
    lv_label_set_long_mode(form_error, LV_LABEL_LONG_DOT);
    text(root(), "1-24 characters. Use English letters, numbers,\nspaces or punctuation. Names must be unique.", 32, 552, 656, 20, MUTED);
    lv_obj_t *keyboard = lv_keyboard_create(root());
    lv_obj_set_align(keyboard, LV_ALIGN_TOP_LEFT);
    lv_obj_set_pos(keyboard, 16, 684);
    lv_obj_set_size(keyboard, 688, 420);
    lv_obj_set_style_text_font(keyboard, font(24), 0);
    lv_keyboard_set_textarea(keyboard, name_input);
    lv_obj_add_event_cb(keyboard, editor_event, LV_EVENT_CANCEL, NULL);
    button(root(), "Save player", 32, 1140, 320, 88, true, "save-player", A_SAVE, 0, NULL);
    button(root(), "Cancel", 368, 1140, 320, 88, false, "cancel-editor", A_CANCEL, 0, "profiles");
}
static void history(void) {
    /* 显示后台查询出的真实对局；点击卡片后请求这局的回放。 */
    shell("Game history", "Real recorded games, including unfinished sessions.");
    int64_t total = ui_json_int(&bridge, bridge.history, "$.total", -1);
    int64_t offset = ui_json_int(&bridge, bridge.history, "$.offset", config.history_offset);
    if(total <= 0) {
        lv_obj_t *card = box(root(), 32, 320, 656, 320, PAPER, 24);
        text(card, total == 0 ? "No saved games yet" : "History is not loaded", 24, 36, 608, 32, INK);
        text(card, total == 0 ? "Completed and interrupted games will appear here." : "Waiting for the local game service.", 24, 124, 608, 24, MUTED);
    } else {
        for(int i = 0; i < 4; ++i) {
            char path[80], white[40], black[40], result[32], state[32], title[128], date[40], mode[16];
            snprintf(path, sizeof(path), "$.games[%d].id", i);
            int64_t id = ui_json_int(&bridge, bridge.history, path, 0);
            if(!id) break;
            snprintf(path, sizeof(path), "$.games[%d].white", i);
            ui_json_text(&bridge, bridge.history, path, white, sizeof(white));
            snprintf(path, sizeof(path), "$.games[%d].black", i);
            ui_json_text(&bridge, bridge.history, path, black, sizeof(black));
            snprintf(path, sizeof(path), "$.games[%d].result", i);
            ui_json_text(&bridge, bridge.history, path, result, sizeof(result));
            snprintf(path, sizeof(path), "$.games[%d].status", i);
            ui_json_text(&bridge, bridge.history, path, state, sizeof(state));
            lv_obj_t *b = button(root(), "", 32, 290+i*190, 656, 166, false, "review-game", A_REVIEW, id, "review");
            snprintf(title, sizeof(title), "%s vs %s", white, black);
            clipped_text(b, title, 24, 22, 608, 28, INK);
            snprintf(title, sizeof(title), "%s / %s", result, state);
            text(b, title, 24, 66, 608, 24, MUTED);
            snprintf(path, sizeof(path), "$.games[%d].created_at", i);
            ui_json_text(&bridge, bridge.history, path, date, sizeof(date));
            snprintf(path, sizeof(path), "$.games[%d].mode", i);
            ui_json_text(&bridge, bridge.history, path, mode, sizeof(mode));
            snprintf(title, sizeof(title), "%s / %s", date, mode);
            clipped_text(b, title, 24, 112, 608, 20, MUTED);
        }
    }
    disable(button(root(), LV_SYMBOL_LEFT " Previous", 32, 1090, 320, 88, false, "previous-history", A_HISTORY_PAGE, -4, NULL), total < 0 || offset <= 0);
    disable(button(root(), "Next " LV_SYMBOL_RIGHT, 368, 1090, 320, 88, false, "next-history", A_HISTORY_PAGE, 4, NULL), total < 0 || offset + 4 >= total);
    status_label = text(root(), "", 32, 1192, 656, 20, RED);
}
static void dropdown_event(lv_event_t *event) {
    lv_obj_t *o = lv_event_get_target(event);
    if(o == port_dropdown) config.port_index = (int)lv_dropdown_get_selected(o);
}
static void draw_position(int x, int y, int size, const char *fen) {
    /* 按 FEN 绘制棋子，用于开局目标图和历史回放。 */
    char pieces[64];
    memset(pieces, '.', sizeof(pieces));
    if(fen) {
        unsigned index = 0;
        for(const char *p = fen; *p && *p != ' ' && index < 64; ++p) {
            if(*p >= '1' && *p <= '8') index += (unsigned)(*p - '0');
            else if(*p != '/') pieces[index++] = *p;
        }
    }
    int cell = size / 8;
    for(int r = 0; r < 8; ++r) {
        char rank[2] = {(char)('8'-r), 0};
        text(root(), rank, x-24, y+r*cell+cell/2-12, 20, 20, MUTED);
        for(int c = 0; c < 8; ++c) {
            int index = r*8+c;
            lv_obj_t *tile = box(root(), x+c*cell, y+r*cell, cell, cell, ((r+c)&1) ? 0xA49B85 : 0xE9E3D5, 0);
            piece_images[index] = lv_image_create(tile);
            lv_obj_center(piece_images[index]);
            if(pieces[index] == '.') lv_obj_add_flag(piece_images[index], LV_OBJ_FLAG_HIDDEN);
            else {
                char path[2048];
                bool white = pieces[index] >= 'A' && pieces[index] <= 'Z';
                char piece = white ? (char)(pieces[index] + ('a'-'A')) : pieces[index];
                snprintf(path, sizeof(path), "P:%s/%s-%c.png", SCB_UI_ASSET_DIR, white ? "white" : "black", piece);
                lv_image_set_src(piece_images[index], path);
            }
        }
    }
    for(int c = 0; c < 8; ++c) {
        char file[2] = {(char)('a'+c), 0};
        text(root(), file, x+c*cell+cell/2-6, y+size+10, 22, 20, MUTED);
    }
}
static void board_setup(void) {
    /* 图中是目标摆放，不是传感器实况；检查占用后还需人工确认棋种。 */
    config.reconnecting = state_flag("$.active");
    shell(config.reconnecting ? "Board connection" : "Set up the board",
          config.reconnecting ? "Reconnect and restore the last accepted position." :
          "Target layout / sensors detect presence, not piece type.");
    text(root(), mode_titles[config.mode], 32, 252, 656, 20, MUTED);
    /* 此处是开局连接，独立 Board test 页复用同一个后台连接。 */
    port_dropdown = lv_dropdown_create(root());
    lv_obj_set_pos(port_dropdown, 32, 300);
    lv_obj_set_size(port_dropdown, 432, 64);
    lv_obj_set_style_text_font(port_dropdown, font(24), 0);
    lv_dropdown_set_options(port_dropdown, "No USB serial ports");
    lv_obj_add_event_cb(port_dropdown, dropdown_event, LV_EVENT_VALUE_CHANGED, NULL);
    port_options[0] = '\0';
    connection_button = button(root(), "Connect board", 480, 300, 208, 64, true, "connect-board", A_CONNECT, 0, NULL);
    lv_obj_set_style_text_font(connection_button, font(24), 0);
    char fen[128];
    bool saved_position = config.reconnecting && ui_json_text(&bridge, bridge.state, "$.fen", fen, sizeof(fen));
    draw_position(144, 390, 432, saved_position ? fen : "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR");
    status_label = text(root(), "", 32, 866, 656, 24, MUTED);
    lv_obj_set_height(status_label, 104);
    lv_label_set_long_mode(status_label, LV_LABEL_LONG_DOT);
    if(config.reconnecting) {
        /* 对局断线时复用连接入口；不会创建新对局或重置当前棋局。 */
        button(root(), "Return to game", 32, 988, 656, 72, true, "return-game", A_NAV, UI_GAME, "game");
        return;
    }
    check_button = button(root(), "Check position", 32, 988, 656, 72, false, "check-position", A_CHECK, 0, NULL);
    verified_button = button(root(), "I verified piece types and colors", 32, 1080, 656, 64, false, "verify-pieces", A_VERIFIED, 0, NULL);
    lv_obj_set_style_text_font(verified_button, font(24), 0);
    start_button = button(root(), "Start game", 32, 1160, 656, 64, true, "start-game", A_START, 0, "game");
}
static void active_game(void) {
    /* 先创建时钟和状态控件，后续由 refresh_live() 更新内容。 */
    shell("Current game", "Live turns, clocks and accepted physical moves.");
    for(int i = 0; i < 2; ++i) {
        lv_obj_t *card = box(root(), 32+i*336, 266, 320, 180, PAPER, 24);
        text(card, i ? "BLACK" : "WHITE", 24, 18, 272, 20, MUTED);
        char name[40];
        ui_json_text(&bridge, bridge.state, i ? "$.black" : "$.white", name, sizeof(name));
        clipped_text(card, name[0] ? name : "Not started", 24, 55, 272, 24, INK);
        clock_labels[i] = text(card, "--:--", 24, 100, 272, 40, INK);
    }
    lv_obj_t *last = box(root(), 32, 472, 656, 96, SOFT, 20);
    text(last, "LAST MOVE", 24, 18, 240, 20, MUTED);
    last_move_label = text(last, "No moves yet", 286, 28, 346, 28, INK);
    lv_obj_t *info = box(root(), 32, 590, 656, 310, PAPER, 24);
    text(info, "GAME STATUS / MOVE FEEDBACK", 24, 20, 608, 20, MUTED);
    status_label = text(info, "", 24, 76, 608, 24, INK);
    lv_obj_set_height(status_label, 160);
    lv_label_set_long_mode(status_label, LV_LABEL_LONG_DOT);
    char mode[16];
    ui_json_text(&bridge, bridge.state, "$.mode", mode, sizeof(mode));
    if(!strcmp(mode, "coach")) {
        for(int i = 0; i < 2; ++i) {
            coaching_buttons[i] = button(info, "", 24+i*312, 248, 296, 48, false,
                                         i ? "game-coach-black" : "game-coach-white", A_COACH, i, NULL);
            lv_obj_set_style_text_font(coaching_buttons[i], font(20), 0);
        }
        hint_button = button(root(), "AI coaching", 32, 940, 208, 80, false, "ai-coaching", A_NAV, UI_COACHING, "coaching");
        lv_obj_set_style_text_font(hint_button, font(24), 0);
    } else if(strcmp(mode, "pvc")) {
        guidance_button = button(info, "Guidance: OFF", 24, 248, 608, 48, false, "game-guidance", A_GUIDANCE, 0, NULL);
        lv_obj_set_style_text_font(guidance_button, font(20), 0);
        hint_button = button(root(), "Hint", 32, 940, 208, 80, false, "hint", A_HINT, 0, NULL);
    }
    if(!strcmp(mode, "pvc")) {
        pause_button = button(root(), "Pause", 32, 940, 320, 80, true, "pause", A_PAUSE, 0, NULL);
        end_button = button(root(), "End", 368, 940, 320, 80, false, "end", A_END, 0, NULL);
    } else {
    pause_button = button(root(), "Pause", 256, 940, 208, 80, true, "pause", A_PAUSE, 0, NULL);
    end_button = button(root(), "End", 480, 940, 208, 80, false, "end", A_END, 0, NULL);
    }
    move_button = button(root(), "Confirm move", 32, 1040, 656, 80, false, "confirm-move", A_CONFIRM_MOVE, 0, "move-editor");
    char first[8];
    bool promotions = ui_json_text(&bridge, bridge.state, "$.promotions[0]", first, sizeof(first));
    if(promotions) {
        lv_obj_add_flag(move_button, LV_OBJ_FLAG_HIDDEN);
        const char *names[] = {"Queen", "Rook", "Bishop", "Knight"};
        const char pieces[] = {'q','r','b','n'};
        char wanted[8];
        ui_json_text(&bridge, bridge.state, "$.computer_move", wanted, sizeof(wanted));
        if(wanted[0]) {
            button(root(), "Computer move / confirm placement", 32, 1040, 656, 80, false,
                   "computer-instructions", A_NAV, UI_INSTRUCTIONS, "instructions");
        } else {
            for(int i = 0; i < 4; ++i) button(root(), names[i], 32+i*168, 1040, 152, 80, false, "promote", A_PROMOTE, pieces[i], NULL);
        }
    }
    lv_obj_t *position = button(root(), "View position", 32, 1140, 320, 80, false, "view-position", A_REVIEW,
                                ui_json_int(&bridge, bridge.state, "$.game_id", 0), "review");
    disable(position, ui_json_int(&bridge, bridge.state, "$.game_id", 0) <= 0);
    disable(button(root(), "Board connection", 368, 1140, 320, 80, false, "game-connection", A_NAV, UI_BOARD_SETUP, "board-setup"),
            !state_flag("$.active"));
}
static void diagnostics(void) {
    /* 固定坐标直接对应固件；未知数据用 ?，不会误画成空盘。 */
    shell("Board / Sensor Test", "Live occupancy only / piece types are not detected.");
    port_dropdown = lv_dropdown_create(root());
    lv_obj_set_pos(port_dropdown, 32, 270);
    lv_obj_set_size(port_dropdown, 432, 72);
    lv_obj_set_style_text_font(port_dropdown, font(24), 0);
    lv_dropdown_set_options(port_dropdown, "No USB serial ports");
    lv_obj_add_event_cb(port_dropdown, dropdown_event, LV_EVENT_VALUE_CHANGED, NULL);
    port_options[0] = '\0';
    connection_button = button(root(), "Connect", 480, 270, 208, 72, true, "connect-board", A_CONNECT, 0, NULL);
    lv_obj_set_style_text_font(connection_button, font(24), 0);
    text(root(), "O = occupied   blank = empty   ? = unavailable", 32, 358, 656, 20, MUTED);
    for(int r = 0; r < 8; ++r) {
        char rank[2] = {(char)('8'-r), 0};
        text(root(), rank, 82, 420+r*62, 24, 20, MUTED);
        for(int c = 0; c < 8; ++c) {
            int square = (7-r)*8+c;
            sensor_tiles[square] = button(root(), "?", 112+c*62, 400+r*62, 62, 62, false,
                                         "sensor-square", A_SQUARE, square, NULL);
            lv_obj_set_style_radius(sensor_tiles[square], 0, 0);
        }
    }
    for(int c = 0; c < 8; ++c) {
        char file[2] = {(char)('a'+c), 0};
        text(root(), file, 136+c*62, 908, 24, 20, MUTED);
    }
    sensor_detail = text(root(), "", 32, 950, 656, 24, INK);
    lv_obj_set_height(sensor_detail, 64);
    sensor_timing = text(root(), "", 32, 1022, 656, 20, MUTED);
    lv_obj_set_height(sensor_timing, 92);
    lv_label_set_long_mode(sensor_timing, LV_LABEL_LONG_DOT);
    scan_button = button(root(), "Scan now", 32, 1132, 208, 80, true, "scan-board", A_SCAN, 0, NULL);
    fault_reset_button = button(root(), "Reset fault", 256, 1132, 208, 80, false, "reset-fault", A_RESET_FAULT, 0, NULL);
    lv_obj_t *current_game = button(root(), "Current game", 480, 1132, 208, 80, false, "sensor-game", A_NAV, UI_GAME, "game");
    lv_obj_set_style_text_font(scan_button, font(20), 0);
    lv_obj_set_style_text_font(fault_reset_button, font(20), 0);
    lv_obj_set_style_text_font(current_game, font(20), 0);
    status_label = text(root(), "", 32, 1220, 656, 20, RED);
    lv_obj_set_height(status_label, 48);
    lv_label_set_long_mode(status_label, LV_LABEL_LONG_DOT);
}
static void coaching_page(void) {
    shell("AI coaching", "Optional online advice / each player decides independently.");
    for(int i = 0; i < 2; ++i) {
        coaching_buttons[i] = button(root(), "", 32+i*336, 278, 320, 80, false,
                                     i ? "game-coach-black" : "game-coach-white", A_COACH, i, NULL);
        lv_obj_set_style_text_font(coaching_buttons[i], font(24), 0);
    }
    lv_obj_t *panel = box(root(), 32, 400, 656, 630, PAPER, 24);
    lv_obj_add_flag(panel, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_scroll_dir(panel, LV_DIR_VER);
    coaching_text = text(panel, "", 24, 28, 608, 24, INK);
    coaching_retry = button(root(), "Request AI advice", 32, 1060, 656, 80, true,
                            "retry-ai-coach", A_COACH_RETRY, 0, NULL);
    text(root(), "Advice does not move pieces or change the game.\nYou can continue if the service is unavailable.", 32, 1166, 656, 20, MUTED);
}
static void instructions(void) {
    shell("Computer move", "Follow the steps on the physical board.");
    char move[8];
    ui_json_text(&bridge, bridge.state, "$.computer_move", move, sizeof(move));
    snprintf(config.instruction_move, sizeof(config.instruction_move), "%s", move);
    text(root(), move[0] ? move : "No computer move pending", 32, 274, 656, 40, INK);
    lv_obj_t *card = box(root(), 32, 352, 656, 600, PAPER, 24);
    char lines[1400] = "", step[256], path[80];
    for(int i = 0; i < 5; ++i) {
        snprintf(path, sizeof(path), "$.computer_action.steps[%d]", i);
        if(!ui_json_text(&bridge, bridge.state, path, step, sizeof(step))) break;
        size_t used = strlen(lines);
        snprintf(lines+used, sizeof(lines)-used, "%d. %s\n\n", i+1, step);
    }
    text(card, lines[0] ? lines : "Waiting for a validated computer move.", 24, 32, 608, 28, INK);
    status_label = text(root(), "", 32, 976, 656, 24, MUTED);
    lv_obj_set_height(status_label, 104);
    lv_label_set_long_mode(status_label, LV_LABEL_LONG_DOT);
    computer_confirm = button(root(), "I placed the specified replacement", 32, 1100, 656, 80, true,
                              "confirm-computer", A_CONFIRM_COMPUTER, 0, NULL);
    lv_obj_set_style_text_font(computer_confirm, font(24), 0);
    automatic_button = button(root(), "Execute automatically", 32, 1100, 656, 80, true,
                              "execute-computer", A_EXECUTE_COMPUTER, 0, NULL);
    lv_obj_set_style_text_font(automatic_button, font(24), 0);
    text(root(), "Hall sensors check occupancy; confirm the actual piece yourself.", 32, 1200, 656, 20, MUTED);
}
static void review(void) {
    /* 显示已保存的局面，Previous/Next 只改变查看的步数。 */
    shell("Review game", "Saved positions / the physical board is not moved.");
    char fen[128], names[120], white[40], black[40];
    bool loaded = ui_json_text(&bridge, bridge.review, "$.fen", fen, sizeof(fen)) &&
                  ui_json_int(&bridge, bridge.review, "$.game_id", 0) == config.review_id;
    ui_json_text(&bridge, bridge.review, "$.white", white, sizeof(white));
    ui_json_text(&bridge, bridge.review, "$.black", black, sizeof(black));
    snprintf(names, sizeof(names), "%s vs %s", white, black);
    text(root(), loaded ? names : "Loading saved game...", 32, 260, 656, 24, MUTED);
    draw_position(64, 330, 592, loaded ? fen : NULL);
    review_move = text(root(), "", 32, 968, 656, 28, INK);
    lv_obj_set_height(review_move, 40);
    lv_label_set_long_mode(review_move, LV_LABEL_LONG_DOT);
    review_count = text(root(), "", 32, 1022, 656, 24, MUTED);
    review_previous = button(root(), LV_SYMBOL_LEFT " Previous", 32, 1100, 320, 96, false, "previous-move", A_REVIEW_STEP, -1, NULL);
    review_next = button(root(), "Next " LV_SYMBOL_RIGHT, 368, 1100, 320, 96, true, "next-move", A_REVIEW_STEP, 1, NULL);
    if(loaded) {
        config.review_ply = ui_json_int(&bridge, bridge.review, "$.ply", 0);
        config.review_total = ui_json_int(&bridge, bridge.review, "$.total", 0);
        char value[96], move[8];
        ui_json_text(&bridge, bridge.review, "$.move", move, sizeof(move));
        lv_label_set_text(review_move, move[0] ? move : "Starting position");
        snprintf(value, sizeof(value), "Position %" PRId64 " of %" PRId64, config.review_ply+1, config.review_total+1);
        lv_label_set_text(review_count, value);
    }
    disable(review_previous, !loaded || config.review_ply <= 0 || config.review_pending);
    disable(review_next, !loaded || config.review_ply >= config.review_total || config.review_pending);
}
static void move_editor(void) {
    /* 传感器走法不明确时输入 UCI；后台仍会检查合法性与实际占用。 */
    shell("Confirm move", "Use this for an ambiguous or special physical move.");
    text(root(), "UCI MOVE / FOR EXAMPLE e2e4", 32, 272, 656, 20, MUTED);
    name_input = lv_textarea_create(root());
    lv_obj_set_pos(name_input, 32, 316);
    lv_obj_set_style_text_font(name_input, font(28), 0);
    lv_obj_set_width(name_input, 656);
    lv_textarea_set_one_line(name_input, true);
    lv_obj_set_height(name_input, 104);
    lv_textarea_set_max_length(name_input, 5);
    lv_textarea_set_placeholder_text(name_input, "e2e4");
    lv_obj_add_event_cb(name_input, editor_event, LV_EVENT_READY, NULL);
    form_error = text(root(), "", 32, 448, 656, 20, RED);
    text(root(), "Finish moving the real pieces first. The service\nchecks legality and the matching occupied squares.", 32, 490, 656, 24, MUTED);
    lv_obj_t *keyboard = lv_keyboard_create(root());
    lv_obj_set_align(keyboard, LV_ALIGN_TOP_LEFT);
    lv_obj_set_pos(keyboard, 16, 684);
    lv_obj_set_size(keyboard, 688, 420);
    lv_obj_set_style_text_font(keyboard, font(24), 0);
    lv_keyboard_set_textarea(keyboard, name_input);
    lv_obj_add_event_cb(keyboard, editor_event, LV_EVENT_CANCEL, NULL);
    button(root(), "Confirm", 32, 1140, 320, 88, true, "save-move", A_SAVE, 0, "game");
    button(root(), "Cancel", 368, 1140, 320, 88, false, "cancel-move", A_NAV, UI_GAME, "game");
}
static void delete_dialog(void) {
    lv_obj_t *overlay = box(root(), 0, 0, 720, 1280, 0x30342D, 0);
    lv_obj_set_style_bg_opa(overlay, 190, 0);
    lv_obj_t *dialog = box(overlay, 32, 390, 656, 450, PAPER, 30);
    text(dialog, "Delete this player?", 32, 32, 592, 32, INK);
    clipped_text(dialog, selected.name, 32, 112, 592, 28, INK);
    text(dialog, "This removes the saved player from this Pi.", 32, 180, 592, 24, MUTED);
    button(dialog, "Delete", 32, 326, 280, 88, true, "confirm-delete", A_CONFIRM_DELETE, deleting_id, NULL);
    button(dialog, "Cancel", 328, 326, 296, 88, false, "cancel-delete", A_CANCEL, 0, "profiles");
}
static void save_player(void) {
    /* 两个表单共用保存入口：走法发给后台，玩家写入 SQLite。 */
    if(current == UI_MOVE_EDITOR && name_input) {
        const char *move = lv_textarea_get_text(name_input);
        size_t n = strlen(move);
        if((n == 4 || n == 5) && move[0] >= 'a' && move[0] <= 'h' && move[1] >= '1' && move[1] <= '8' &&
           move[2] >= 'a' && move[2] <= 'h' && move[3] >= '1' && move[3] <= '8' && (n == 4 || strchr("qrbn", move[4]))) {
            if(command("{\"cmd\":\"commit\",\"move\":\"%s\"}", move)) scb_ui_show(UI_GAME);
            else if(form_error) lv_label_set_text(form_error, local_notice);
        } else if(form_error) lv_label_set_text(form_error, "Use e2e4 or e7e8q (lowercase).");
        return;
    }
    if(!name_input || current != UI_PLAYER_EDITOR) return;
    const char *name = lv_textarea_get_text(name_input);
    bool ok = editing_id ? player_store_rename(&store, editing_id, name) : player_store_create(&store, name);
    if(ok) {
        page_offset = 0;
        scb_ui_show(UI_PROFILES);
    } else lv_label_set_text(form_error, store.error);
}
static void editor_event(lv_event_t *event) {
    if(lv_event_get_code(event) == LV_EVENT_CANCEL) scb_ui_show(current == UI_MOVE_EDITOR ? UI_GAME : UI_PROFILES);
    else save_player();
}
static void operation_error(const char *message) {
    char saved[sizeof(store.error)];
    snprintf(saved, sizeof(saved), "%s", message);
    scb_ui_show(UI_PROFILES);
    lv_obj_t *overlay = box(root(), 0, 0, 720, 1280, 0x30342D, 0);
    lv_obj_set_style_bg_opa(overlay, 190, 0);
    lv_obj_t *dialog = box(overlay, 32, 390, 656, 450, PAPER, 30);
    text(dialog, "Player could not be updated", 32, 32, 592, 28, INK);
    lv_obj_t *detail = text(dialog, saved, 32, 112, 592, 24, RED);
    lv_obj_set_height(detail, 180);
    lv_label_set_long_mode(detail, LV_LABEL_LONG_DOT);
    button(dialog, "Close", 32, 326, 592, 88, true, "close-error", A_CANCEL, 0, "profiles");
}
static bool service_online(void) {
    return bridge.connected && bridge.state[0] && (uint32_t)(lv_tick_get() - bridge.last_state) < 2000;
}
static bool state_flag(const char *path) { return service_online() && ui_json_int(&bridge, bridge.state, path, 0) != 0; }
static void label_value(lv_obj_t *label, const char *value) {
    if(label && strcmp(lv_label_get_text(label), value)) lv_label_set_text(label, value);
}
static void button_value(lv_obj_t *button_object, const char *value) {
    if(button_object) label_value(lv_obj_get_child(button_object, 0), value);
}
static bool command(const char *format, ...) {
    /* 把用户操作排入本机通信队列；发送成功不等于后台执行成功。 */
    char request[1024];
    va_list arguments;
    va_start(arguments, format);
    int n = vsnprintf(request, sizeof(request), format, arguments);
    va_end(arguments);
    local_notice[0] = '\0';
    if(n < 0 || (size_t)n >= sizeof(request) || !ui_bridge_send(&bridge, "%s", request)) {
        snprintf(local_notice, sizeof(local_notice), "%s", bridge.error[0] ? bridge.error : "Game service unavailable.");
        label_value(status_label, local_notice);
        return false;
    }
    return true;
}
static void request_history(void) { command("{\"cmd\":\"history\",\"offset\":%d}", config.history_offset); }
static void end_dialog(void) {
    end_dialog_open = true;
    lv_obj_t *overlay = box(root(), 0, 0, 720, 1280, 0x30342D, 0);
    lv_obj_set_style_bg_opa(overlay, 190, 0);
    lv_obj_t *dialog = box(overlay, 32, 280, 656, 740, PAPER, 30);
    text(dialog, "End game / record result", 32, 32, 592, 28, INK);
    const char *names[] = {"End without a result", "White wins", "Black wins", "Draw"};
    for(int i = 0; i < 4; ++i)
        button(dialog, names[i], 32, 120+i*112, 592, 88, i != 0, "confirm-end", A_CONFIRM_END, i, NULL);
    button(dialog, "Cancel", 32, 600, 592, 88, false, "cancel-end", A_CANCEL, 0, NULL);
}
static void refresh_live(void) {
    /* 根据后台状态更新文字和按钮，避免每次更新都重建整个页面。 */
    bool online = service_online(), active = state_flag("$.active"), paused = state_flag("$.paused");
    bool known = state_flag("$.board_known"), board_connected = state_flag("$.board_connected");
    char message[2048], error[512], value[256], mode[16];
    ui_json_text(&bridge, bridge.state, "$.mode", mode, sizeof(mode));
    message[0] = error[0] = '\0';
    if(local_notice[0]) snprintf(message, sizeof(message), "%s", local_notice);
    else if(!online) snprintf(message, sizeof(message), "Game service unavailable. Launch with pi5/start.sh ui.");
    else if(ui_json_text(&bridge, bridge.state, "$.error", error, sizeof(error)) && error[0]) snprintf(message, sizeof(message), "%s", error);
    else ui_json_text(&bridge, bridge.state, "$.message", message, sizeof(message));
    if(current == UI_HOME) {
        if(!local_notice[0] && online && !error[0]) snprintf(message, sizeof(message), "%s / %s", board_connected ? "Board connected" : "Board not connected", active ? paused ? "Game paused" : "Game in progress" : "No active game");
        if(continue_button) disable(continue_button, !online || ui_json_int(&bridge, bridge.state, "$.game_id", 0) <= 0);
    }
    if(current == UI_BOARD_SETUP) {
        /* 新鲜占用匹配且人工确认后才启用 Start，后台还会再次检查。 */
        bool ready = state_flag("$.ready") && known;
        if(!ready) config.verified = false;
        if(check_button) disable(check_button, !online || !board_connected || state_flag("$.usb_busy"));
        if(start_button) disable(start_button, !ready || !config.verified || active);
        if(verified_button) {
            disable(verified_button, !ready);
            button_value(verified_button, config.verified ? "Verified: piece types and colors" : "I verified piece types and colors");
            lv_obj_set_style_bg_color(verified_button, lv_color_hex(config.verified ? 0xE6EEE7 : SOFT), 0);
        }
    }
    if(current == UI_GAME) {
        char fen[128], move[8], hint[1400], promotion[8], wanted[8], engine_error[512];
        ui_json_text(&bridge, bridge.state, "$.fen", fen, sizeof(fen));
        ui_json_text(&bridge, bridge.state, "$.last_move", move, sizeof(move));
        ui_json_text(&bridge, bridge.state, "$.hint", hint, sizeof(hint));
        ui_json_text(&bridge, bridge.state, "$.computer_move", wanted, sizeof(wanted));
        ui_json_text(&bridge, bridge.state, "$.engine_error", engine_error, sizeof(engine_error));
        if(!online) label_value(title_label, "Service disconnected");
        else if(!active) label_value(title_label, ui_json_int(&bridge, bridge.state, "$.game_id", 0) > 0 ? "Game ended" : "No active game");
        else label_value(title_label, paused ? "Game paused" : strstr(fen, " w ") ? "White to move" : "Black to move");
        for(int i = 0; i < 2; ++i) {
            int64_t ms = ui_json_int(&bridge, bridge.state, i ? "$.black_ms" : "$.white_ms", -1);
            if(ms < 0 || !online) snprintf(value, sizeof(value), "--:--");
            else snprintf(value, sizeof(value), "%02" PRId64 ":%02" PRId64, (ms+999)/60000, ((ms+999)/1000)%60);
            label_value(clock_labels[i], value);
        }
        label_value(last_move_label, move[0] ? move : "No moves yet");
        if(active && !paused && !state_flag("$.motion_active") && !state_flag("$.restore") && !state_flag("$.ambiguous") && !error[0] && !local_notice[0]) {
            if(engine_error[0]) snprintf(message, sizeof(message), "%s unavailable: %s", !strcmp(mode, "coach") ? "AI coaching" : "Stockfish", engine_error);
            else if(wanted[0] && !state_flag("$.restore"))
                snprintf(message, sizeof(message), "Stockfish plays %s.\nOpen Computer move for physical steps.", wanted);
            else if((config.show_hint || !strcmp(mode, "coach")) && hint[0] && !state_flag("$.restore")) snprintf(message, sizeof(message), "%s", hint);
        }
        char game_status[160], source[8], destination[8], path[80];
        ui_json_text(&bridge, bridge.state, "$.game_status", game_status, sizeof(game_status));
        if(game_status[0] && !paused && !state_flag("$.restore") && !error[0]) {
            size_t used = strlen(message);
            snprintf(message+used, sizeof(message)-used, "\n%s", game_status);
        }
        if(state_flag("$.guidance") && !state_flag("$.restore") && !paused && !error[0] &&
           ui_json_text(&bridge, bridge.state, "$.legal_source", source, sizeof(source)) && source[0]) {
            snprintf(message, sizeof(message), "Lifted %s / legal destinations:", source);
            bool any = false;
            for(int i = 0; i < 27; ++i) {
                snprintf(path, sizeof(path), "$.legal_destinations[%d]", i);
                if(!ui_json_text(&bridge, bridge.state, path, destination, sizeof(destination))) break;
                size_t used = strlen(message);
                snprintf(message+used, sizeof(message)-used, "%s%s", any ? ", " : " ", destination);
                any = true;
            }
            if(!any) strncat(message, " none", sizeof(message)-strlen(message)-1);
        }
        bool has_promotion = ui_json_text(&bridge, bridge.state, "$.promotions[0]", promotion, sizeof(promotion));
        bool promotion_controls = false;
        for(unsigned i = 0; i < hit_count; ++i) if(hits[i].action == A_PROMOTE || !strcmp(hits[i].id, "computer-instructions")) promotion_controls = true;
        if(!end_dialog_open && has_promotion != promotion_controls) {
            scb_ui_show(UI_GAME);
            return;
        }
        if(hint_button) disable(hint_button, !active || (strcmp(mode, "coach") && (paused || !state_flag("$.synced") || state_flag("$.thinking"))));
        bool clock_expired = ui_json_int(&bridge, bridge.state, "$.white_ms", -1) == 0 ||
                             ui_json_int(&bridge, bridge.state, "$.black_ms", -1) == 0;
        disable(pause_button, !active || (paused && (!state_flag("$.synced") || clock_expired)));
        disable(end_button, !active);
        disable(move_button, !active || paused || !known || state_flag("$.motion_busy"));
        button_value(pause_button, paused ? "Resume" : "Pause");
        if(guidance_button) {
            button_value(guidance_button, state_flag("$.guidance") ? "Guidance: ON" : "Guidance: OFF");
            disable(guidance_button, !active);
        }
        button_value(move_button, wanted[0] ? "Computer move / instructions" : "Confirm move");
    }
    if(current == UI_GAME || current == UI_COACHING) {
        for(int i = 0; i < 2; ++i) if(coaching_buttons[i]) {
            snprintf(value, sizeof(value), "%s AI: %s", i ? "Black" : "White", state_flag(i ? "$.coach_black" : "$.coach_white") ? "ON" : "OFF");
            button_value(coaching_buttons[i], value);
            disable(coaching_buttons[i], !active || !online || strcmp(mode, "coach"));
        }
    }
    if(current == UI_COACHING) {
        char hint[1400], problem[512];
        ui_json_text(&bridge, bridge.state, "$.hint", hint, sizeof(hint));
        ui_json_text(&bridge, bridge.state, "$.engine_error", problem, sizeof(problem));
        const char *advice = !online ? "Game service unavailable." : !active ? "No active coaching game." :
            strcmp(mode, "coach") ? "AI coaching is available in With coaching mode." :
            !state_flag("$.coaching_enabled") ? "The current player has AI coaching OFF." :
            problem[0] ? problem : state_flag("$.thinking") ? "AI coach is thinking. You can keep playing." : hint[0] ? hint :
            "No AI advice yet. Request advice when the board is synchronized.";
        label_value(coaching_text, advice);
        disable(coaching_retry, !online || !active || paused || !state_flag("$.coaching_enabled") || !state_flag("$.synced") || state_flag("$.thinking"));
        button_value(coaching_retry, problem[0] ? "Retry AI advice" : "Request AI advice");
    }
    if(current == UI_BOARD_SETUP || current == UI_DIAGNOSTICS) {
        char options[sizeof(port_options)] = "", path[80], port[128];
        int count = 0;
        for(int i = 0; i < 8; ++i) {
            snprintf(path, sizeof(path), "$.ports[%d].port", i);
            if(!ui_json_text(&bridge, bridge.state, path, port, sizeof(port))) break;
            size_t used = strlen(options);
            snprintf(options+used, sizeof(options)-used, "%s%s", i ? "\n" : "", port);
            ++count;
        }
        if(!count) snprintf(options, sizeof(options), "No USB serial ports");
        if(strcmp(options, port_options)) {
            snprintf(port_options, sizeof(port_options), "%s", options);
            lv_dropdown_set_options(port_dropdown, options);
            if(config.port_index >= count) config.port_index = 0;
            lv_dropdown_set_selected(port_dropdown, (uint32_t)config.port_index);
        }
        disable(port_dropdown, !online || board_connected || state_flag("$.usb_busy") || !count);
        disable(connection_button, !online || state_flag("$.usb_busy") || (!count && !board_connected));
        button_value(connection_button, board_connected ? "Disconnect" : current == UI_DIAGNOSTICS ? "Connect" : "Connect board");
        if(online && !error[0] && !local_notice[0] && !board_connected)
            snprintf(message, sizeof(message), "Choose a USB port above, then connect the board.");
    }
    if(current == UI_DIAGNOSTICS) {
        char mask_text[32], expected_text[32];
        uint64_t mask = 0, expected = 0;
        if(known && ui_json_text(&bridge, bridge.state, "$.board", mask_text, sizeof(mask_text))) mask = strtoull(mask_text, NULL, 16);
        bool compare = known && ui_json_text(&bridge, bridge.state, "$.expected_board", expected_text, sizeof(expected_text));
        if(compare) expected = strtoull(expected_text, NULL, 16);
        for(int i = 0; i < 64; ++i) {
            bool occupied = known && ((mask >> i) & 1);
            button_value(sensor_tiles[i], !known ? "?" : occupied ? "O" : "");
            uint32_t color = !known ? 0xE6E5DF : occupied ? 0xCEDECE : ((i/8+i%8)&1) ? 0xA49B85 : 0xE9E3D5;
            lv_obj_set_style_bg_color(sensor_tiles[i], lv_color_hex(color), 0);
            lv_obj_set_style_border_width(sensor_tiles[i], compare && (((mask ^ expected) >> i) & 1) ? 3 : 0, 0);
            lv_obj_set_style_border_color(sensor_tiles[i], lv_color_hex(RED), 0);
        }
        int q = config.selected_square;
        snprintf(value, sizeof(value), "%c%d: %s / %s", 'a'+q%8, q/8+1, !known ? "Unavailable" : ((mask>>q)&1) ? "Occupied" : "Empty",
                 !known ? "No fresh sensor data" : compare ? mask == expected ? "Board matches" : "Red border = mismatch" : "No game position to compare");
        label_value(sensor_detail, value);
        int64_t period = ui_json_int(&bridge, bridge.state, "$.scan_timing.frame_us", -1);
        int64_t debounce = ui_json_int(&bridge, bridge.state, "$.scan_timing.debounce_us", -1);
        int64_t round_trip = ui_json_int(&bridge, bridge.state, "$.scan_round_trip_ms", -1);
        if(online && board_connected && period > 0)
            snprintf(value, sizeof(value), "MCU scan period: %.2f ms / %.1f Hz\nDebounce: %.2f ms / USB round trip: %" PRId64 " ms", period/1000.0, 1000000.0/period, debounce/1000.0, round_trip);
        else snprintf(value, sizeof(value), "Scan timing unavailable. Connect and press Scan now.");
        label_value(sensor_timing, value);
        disable(scan_button, !online || !board_connected || state_flag("$.usb_busy"));
        char fault[256];
        ui_json_text(&bridge, bridge.state, "$.fault", fault, sizeof(fault));
        disable(fault_reset_button, !online || !board_connected || !fault[0] || state_flag("$.usb_busy") || state_flag("$.motion_busy"));
        char diagnostic_error[160];
        if(ui_json_text(&bridge, bridge.state, "$.diagnostic_error", diagnostic_error, sizeof(diagnostic_error)) && diagnostic_error[0])
            snprintf(message, sizeof(message), "%s", diagnostic_error);
        else if(online && !error[0]) snprintf(message, sizeof(message), "%s", !known ? "Occupancy unavailable / no fresh scan" : mask ? "Live sensor data / tap a square" : "Empty board / valid sensor data");
    }
    if(current == UI_INSTRUCTIONS) {
        char wanted[8], replacement[32];
        ui_json_text(&bridge, bridge.state, "$.computer_move", wanted, sizeof(wanted));
        if(online && strcmp(wanted, config.instruction_move)) {
            scb_ui_show(UI_GAME);
            return;
        }
        bool replacement_needed = ui_json_text(&bridge, bridge.state, "$.computer_action.replacement", replacement, sizeof(replacement));
        if(replacement_needed) {
            lv_obj_remove_flag(computer_confirm, LV_OBJ_FLAG_HIDDEN);
            snprintf(value, sizeof(value), "I placed the %s", replacement);
            button_value(computer_confirm, value);
        } else lv_obj_add_flag(computer_confirm, LV_OBJ_FLAG_HIDDEN);
        disable(computer_confirm, !active || paused || !known || !replacement_needed || state_flag("$.restore") || !state_flag("$.computer_action.placement_matches"));
        bool automatic = state_flag("$.automatic_motion_enabled") && state_flag("$.computer_action.automatic_eligible");
        if(automatic) lv_obj_remove_flag(automatic_button, LV_OBJ_FLAG_HIDDEN);
        else lv_obj_add_flag(automatic_button, LV_OBJ_FLAG_HIDDEN);
        disable(automatic_button, !online || !active || paused || !state_flag("$.synced") || state_flag("$.motion_busy") || state_flag("$.usb_busy"));
        if(!wanted[0] && online && !error[0]) snprintf(message, sizeof(message), "No computer move pending. Return to the game.");
    }
    if(current == UI_REVIEW && error[0]) label_value(review_move, error);
    char board_fault[256];
    if((current == UI_BOARD_SETUP || current == UI_GAME || current == UI_DIAGNOSTICS || current == UI_INSTRUCTIONS) && ui_json_text(&bridge, bridge.state, "$.fault", board_fault, sizeof(board_fault)) && board_fault[0])
        snprintf(message, sizeof(message), "Fault: %.150s. Resolve it; Board Test > Reset fault, then Resume.", board_fault);
    label_value(status_label, message);
}
static void click(lv_event_t *event) {
    /* 按绑定的 Action 分发点击；改设置、切页面或向后台发请求。 */
    Hit hit = *(Hit *)lv_event_get_user_data(event);
    if(lv_obj_has_state(hit.obj, LV_STATE_DISABLED)) return;
    switch(hit.action) {
        case A_NONE: break;
        case A_NAV:
            if(hit.value == UI_PROFILES && current == UI_HOME) config.pick_side = -1;
            scb_ui_show((UiScreen)hit.value);
            if(hit.value == UI_HISTORY) request_history();
            break;
        case A_SELECT:
            if(!player_store_select(&store, hit.value)) operation_error(store.error);
            else scb_ui_show(UI_PROFILES);
            break;
        case A_NEW: editing_id = 0; scb_ui_show(UI_PLAYER_EDITOR); break;
        case A_EDIT: editing_id = selected.id; scb_ui_show(UI_PLAYER_EDITOR); break;
        case A_SAVE: save_player(); break;
        case A_CANCEL: scb_ui_show(current == UI_PLAYER_EDITOR ? UI_PROFILES : current); break;
        case A_DELETE: deleting_id = hit.value; delete_dialog(); break;
        case A_CONFIRM_DELETE:
            if(!player_store_delete(&store, hit.value)) operation_error(store.error);
            else scb_ui_show(UI_PROFILES);
            break;
        case A_PAGE:
            page_offset += (int)hit.value * SCB_PLAYER_PAGE_SIZE;
            if(page_offset < 0) page_offset = 0;
            scb_ui_show(UI_PROFILES);
            break;
        case A_RETRY:
            player_store_close(&store);
            player_store_open(&store, database_path);
            scb_ui_show(UI_PROFILES);
            break;
        case A_MODE: config.mode = (int)hit.value; scb_ui_show(UI_SETUP); break;
        case A_SIDE: {
            ScbPlayer human = config.human ? config.black : config.white;
            config.human = (int)hit.value;
            if(config.human) config.black = human;
            else config.white = human;
            scb_ui_show(UI_SETUP); break;
        }
        case A_CLOCK: config.minutes = (int)hit.value; scb_ui_show(UI_SETUP); break;
        case A_PICK: config.pick_side = (int)hit.value; scb_ui_show(UI_PROFILES); break;
        case A_USE_PLAYER:
            if(config.pick_side == 1 || (config.pick_side < 0 && config.mode == 1 && config.human)) config.black = selected;
            else config.white = selected;
            config.pick_side = -1;
            scb_ui_show(UI_SETUP); break;
        case A_PREPARE:
            if(config.mode == 2 && (config.coach[0] < 0 || config.coach[1] < 0)) {
                snprintf(local_notice, sizeof(local_notice), "White and Black must each choose AI coaching ON or OFF.");
                label_value(status_label, local_notice);
                break;
            }
            if((config.mode != 1 && (!config.white.id || !config.black.id || config.white.id == config.black.id)) ||
               (config.mode == 1 && !(config.human ? config.black.id : config.white.id))) {
                snprintf(local_notice, sizeof(local_notice), "%s", config.mode == 1 ? "Choose a saved human player." : "Choose two different saved players.");
                label_value(status_label, local_notice);
                break;
            }
            config.verified = false;
            config.show_hint = config.mode == 2;
            if(command("{\"cmd\":\"prepare\",\"mode\":\"%s\",\"white_id\":%" PRId64 ",\"black_id\":%" PRId64 ",\"human\":\"%s\",\"minutes\":%d,\"guidance\":%s,\"coach_white\":%s,\"coach_black\":%s}",
                mode_codes[config.mode], config.white.id, config.black.id, config.human ? "b" : "w", config.minutes, config.mode == 0 && config.guidance ? "true" : "false",
                config.coach[0] == 1 ? "true" : "false", config.coach[1] == 1 ? "true" : "false")) scb_ui_show(UI_BOARD_SETUP);
            break;
        case A_CHECK: config.verified = false; command("{\"cmd\":\"check\"}"); break;
        case A_VERIFIED: config.verified = !config.verified; refresh_live(); break;
        case A_START: command("{\"cmd\":\"start\",\"verified\":%s}", config.verified ? "true" : "false"); break;
        case A_PAUSE: command(state_flag("$.paused") ? "{\"cmd\":\"resume\"}" : "{\"cmd\":\"pause\"}"); break;
        case A_END: end_dialog(); break;
        case A_CONFIRM_END: {
            const char *results[] = {"*", "1-0", "0-1", "1/2-1/2"};
            if(command("{\"cmd\":\"end\",\"result\":\"%s\"}", results[hit.value])) {
                config.ending = true;
                scb_ui_show(UI_GAME);
            }
            break;
        }
        case A_COACH:
            if(current == UI_SETUP) {
                config.coach[hit.value / 2] = (int)(hit.value % 2);
                scb_ui_show(UI_SETUP);
            } else command("{\"cmd\":\"coaching\",\"side\":\"%s\",\"enabled\":%s}", hit.value ? "b" : "w",
                           state_flag(hit.value ? "$.coach_black" : "$.coach_white") ? "false" : "true");
            break;
        case A_COACH_RETRY: command("{\"cmd\":\"hint\"}"); break;
        case A_HINT: config.show_hint = true; command("{\"cmd\":\"hint\"}"); break;
        case A_GUIDANCE:
            if(current == UI_SETUP) { config.guidance = !config.guidance; scb_ui_show(UI_SETUP); }
            else command("{\"cmd\":\"guidance\",\"enabled\":%s}", state_flag("$.guidance") ? "false" : "true");
            break;
        case A_SCAN: command("{\"cmd\":\"scan\"}"); break;
        case A_RESET_FAULT: command("{\"cmd\":\"reset_fault\"}"); break;
        case A_EXECUTE_COMPUTER: {
            char move[8];
            if(ui_json_text(&bridge, bridge.state, "$.computer_move", move, sizeof(move)))
                command("{\"cmd\":\"execute_computer\",\"move\":\"%s\"}", move);
            break;
        }
        case A_SQUARE: config.selected_square = (int)hit.value; refresh_live(); break;
        case A_CONFIRM_COMPUTER: {
            char move[8];
            if(ui_json_text(&bridge, bridge.state, "$.computer_move", move, sizeof(move)))
                command("{\"cmd\":\"confirm_computer\",\"move\":\"%s\"}", move);
            break;
        }
        case A_CONFIRM_MOVE:
            { char wanted[8];
              ui_json_text(&bridge, bridge.state, "$.computer_move", wanted, sizeof(wanted));
              scb_ui_show(wanted[0] ? UI_INSTRUCTIONS : UI_MOVE_EDITOR); }
            break;
        case A_PROMOTE: {
            char move[8];
            if(ui_json_text(&bridge, bridge.state, "$.promotions[0]", move, sizeof(move))) {
                move[4] = (char)hit.value; move[5] = '\0';
                command("{\"cmd\":\"commit\",\"move\":\"%s\"}", move);
            }
            break;
        }
        case A_CONNECT:
            if(state_flag("$.board_connected")) command("{\"cmd\":\"disconnect\"}");
            else {
                char path[80], port[128], quoted[800];
                snprintf(path, sizeof(path), "$.ports[%d].port", config.port_index);
                if(ui_json_text(&bridge, bridge.state, path, port, sizeof(port)) && ui_json_quote(&bridge, port, quoted, sizeof(quoted)))
                    command("{\"cmd\":\"connect\",\"port\":%s}", quoted);
            }
            break;
        case A_HISTORY_PAGE:
            config.history_offset += (int)hit.value;
            if(config.history_offset < 0) config.history_offset = 0;
            request_history(); break;
        case A_REVIEW:
            config.review_return = current == UI_GAME ? UI_GAME : UI_HISTORY;
            config.review_id = hit.value;
            config.review_ply = current == UI_GAME ? 1000000 : 0;
            config.review_pending = true;
            bridge.review[0] = '\0';
            command("{\"cmd\":\"review\",\"game_id\":%" PRId64 ",\"ply\":%" PRId64 "}", config.review_id, config.review_ply);
            scb_ui_show(UI_REVIEW); break;
        case A_REVIEW_STEP:
            config.review_pending = true;
            command("{\"cmd\":\"review\",\"game_id\":%" PRId64 ",\"ply\":%" PRId64 "}", config.review_id, config.review_ply+hit.value);
            disable(review_previous, true); disable(review_next, true); break;
    }
}
void scb_ui_show(UiScreen screen) {
    /* 页面编号相当于路由，决定调用哪个页面创建函数。 */
    current = screen;
    switch(screen) {
        case UI_HOME: home(); break;
        case UI_SETUP: setup(); break;
        case UI_PROFILES: profiles(); break;
        case UI_HISTORY: history(); break;
        case UI_PLAYER_EDITOR: player_editor(); break;
        case UI_BOARD_SETUP: board_setup(); break;
        case UI_GAME: active_game(); break;
        case UI_REVIEW: review(); break;
        case UI_MOVE_EDITOR: move_editor(); break;
        case UI_DIAGNOSTICS: diagnostics(); break;
        case UI_INSTRUCTIONS: instructions(); break;
        case UI_COACHING: coaching_page(); break;
        default: break;
    }
    refresh_live();
    lv_obj_update_layout(root());
}
void scb_ui_init(const char *path) {
    /* 打开玩家库、初始化本机通信，再显示首页。 */
    page_offset = 0;
    editing_id = deleting_id = 0;
    memset(&config, 0, sizeof(config));
    config.minutes = 10;
    config.coach[0] = config.coach[1] = -1;
    config.pick_side = -1;
    config.review_return = UI_HISTORY;
    local_notice[0] = '\0';
    player_store_open(&store, path);
    snprintf(database_path, sizeof(database_path), "%s", store.path);
    ui_bridge_init(&bridge, getenv("SCB_UI_TEST_MODE") != NULL);
    scb_ui_show(UI_HOME);
}
void scb_ui_shutdown(void) { ui_bridge_close(&bridge); player_store_close(&store); }
void scb_ui_preview_setup(int mode) {
    /* 仅供离线版式渲染，不向后台发送设置。 */
    if(!bridge.disabled || mode < 0 || mode > 2) return;
    config.mode = mode;
    scb_ui_show(UI_SETUP);
}
void scb_ui_text_input(const char *value) {
    if((current == UI_PLAYER_EDITOR || current == UI_MOVE_EDITOR) && name_input) lv_textarea_add_text(name_input, value);
}
void scb_ui_backspace(void) {
    if((current == UI_PLAYER_EDITOR || current == UI_MOVE_EDITOR) && name_input) lv_textarea_delete_char(name_input);
}
void scb_ui_submit(void) { save_player(); }
void scb_ui_tick(void) {
    /* 主循环反复调用：收后台消息，按结果跳转并更新实时显示。 */
    last_changes = ui_bridge_poll(&bridge, lv_tick_get());
    if((last_changes & SCB_BRIDGE_HISTORY) && current == UI_HISTORY) scb_ui_show(UI_HISTORY);
    if((last_changes & SCB_BRIDGE_REVIEW) && current == UI_REVIEW) {
        config.review_pending = false;
        scb_ui_show(UI_REVIEW);
    }
    if(state_flag("$.active") && current == UI_BOARD_SETUP && !config.reconnecting) scb_ui_show(UI_GAME);
    if(config.ending && service_online() && !state_flag("$.active")) {
        config.ending = false;
        config.history_offset = 0;
        scb_ui_show(UI_HISTORY);
        request_history();
    }
    uint32_t now = lv_tick_get();
    if(last_changes || (uint32_t)(now - last_live_refresh) >= 200) {
        refresh_live();
        last_live_refresh = now;
    }
}
const char *scb_ui_screen_name(UiScreen screen) { return screen_names[screen]; }
void scb_ui_write_hotspots(FILE *out) {
    fputc('[', out);
    bool first = true;
    for(unsigned i = 0; i < hit_count; ++i) {
        Hit *hit = &hits[i];
        if(!hit->target) continue;
        lv_area_t a;
        lv_obj_get_coords(hit->obj, &a);
        if(!first) fputc(',', out);
        first = false;
        fprintf(out, "{\"id\":\"%s\",\"target\":\"%s\",\"x\":%d,\"y\":%d,\"w\":%d,\"h\":%d,\"disabled\":%s}",
                hit->id, hit->target, (int)a.x1, (int)a.y1, (int)(a.x2-a.x1+1), (int)(a.y2-a.y1+1),
                lv_obj_has_state(hit->obj, LV_STATE_DISABLED) ? "true" : "false");
    }
    fputc(']', out);
}
static bool press(const char *id) {
    for(unsigned i = 0; i < hit_count; ++i) {
        if(!strcmp(hits[i].id, id)) {
            lv_obj_send_event(hits[i].obj, LV_EVENT_CLICKED, NULL);
            return true;
        }
    }
    fprintf(stderr, "Missing UI action: %s\n", id);
    return false;
}
static bool label_bounds(lv_obj_t *parent) {
    lv_area_t bounds;
    lv_obj_get_coords(parent, &bounds);
    for(uint32_t i = 0; i < lv_obj_get_child_count(parent); ++i) {
        lv_obj_t *child = lv_obj_get_child(parent, i);
        if(lv_obj_check_type(child, &lv_label_class) && lv_label_get_text(child)[0]) {
            lv_area_t a;
            lv_obj_get_coords(child, &a);
            if(a.x1 < bounds.x1 || a.x2 > bounds.x2 ||
               (!lv_obj_has_flag(parent, LV_OBJ_FLAG_SCROLLABLE) && (a.y1 < bounds.y1 || a.y2 > bounds.y2))) {
                fprintf(stderr, "Text outside parent: %s\n", lv_label_get_text(child));
                return false;
            }
        }
        if(!label_bounds(child)) return false;
    }
    return true;
}
bool scb_ui_smoke_test(void) {
    /* The host supplies an isolated temporary database for this test. */
    if(!data_ok || player_count || selected.id) return false;
    if(!press("diagnostics") || current != UI_DIAGNOSTICS || !press("back") || current != UI_HOME) return false;
    if(!press("new-game") || current != UI_SETUP) return false;
    if(!press("mode-computer") || config.mode != 1) return false;
    for(unsigned i = 0; i < hit_count; ++i) if(hits[i].action == A_GUIDANCE) return false;
    if(!press("clock-five") || config.minutes != 5) return false;
    if(!press("choose-white") || current != UI_PROFILES) return false;
    if(!press("create-player") || !name_input) return false;
    lv_textarea_set_text(name_input, "   ");
    if(!press("save-player") || current != UI_PLAYER_EDITOR || !lv_label_get_text(form_error)[0]) return false;
    lv_textarea_set_text(name_input, "UI test player");
    if(!press("save-player") || current != UI_PROFILES || strcmp(selected.name, "UI test player")) return false;
    int64_t id = selected.id;
    if(!press("rename-player") || !name_input) return false;
    lv_textarea_set_text(name_input, "Renamed test player");
    if(!press("save-player") || strcmp(selected.name, "Renamed test player")) return false;
    char path[sizeof(database_path)];
    snprintf(path, sizeof(path), "%s", database_path);
    scb_ui_shutdown();
    scb_ui_init(path);
    if(selected.id != id || strcmp(selected.name, "Renamed test player")) return false;
    if(!press("players") || !press("delete-player") || !press("cancel-delete") || player_count != 1) return false;
    if(!press("delete-player") || !press("confirm-delete") || selected.id || player_count) return false;
    for(int i = 0; i < 6; ++i) {
        char name[25];
        snprintf(name, sizeof(name), "Long player name %07d", i);
        if(!player_store_create(&store, name)) return false;
    }
    scb_ui_show(UI_PROFILES);
    if(row_count != 4 || !press("next-players") || page_offset != 4 || row_count != 2) return false;
    if(!press("select-player") || selected.id != rows[0].id) return false;
    if(!press("previous-players") || page_offset) return false;
    if(!press("delete-player")) return false;
    lv_refr_now(NULL);
    if(!label_bounds(root()) || !press("cancel-delete")) return false;
    for(int i = 0; i < UI_SCREEN_COUNT; ++i) {
        scb_ui_show((UiScreen)i);
        lv_refr_now(NULL);
        if(!label_bounds(root())) return false;
        for(unsigned j = 0; j < hit_count; ++j) {
            lv_area_t a;
            lv_obj_get_coords(hits[j].obj, &a);
            if(a.x1 < 0 || a.y1 < 0 || a.x2 >= 720 || a.y2 >= 1280) return false;
        }
    }
    scb_ui_show(UI_SETUP);
    if(!press("mode-coach") || config.coach[0] != -1 || config.coach[1] != -1) return false;
    if(!press("prepare") || current != UI_SETUP || !strstr(lv_label_get_text(status_label), "each choose")) return false;
    if(!press("coach-white-on") || !press("coach-black-off") || config.coach[0] != 1 || config.coach[1] != 0) return false;
    lv_refr_now(NULL);
    if(!label_bounds(root())) return false;
    /* 仅在隔离测试里注入长名字、长说明和占用，检查有数据时的版式。 */
    bridge.connected = true;
    bridge.last_state = lv_tick_get();
    snprintf(bridge.state, sizeof(bridge.state), "{\"active\":true,\"board_connected\":true,\"board_known\":true,\"board\":\"FFFF00000000FFFF\",\"expected_board\":\"FFFF00000000FFFF\",\"guidance\":true,\"white\":\"Long player name 12345678\",\"black\":\"Another long player name\",\"fen\":\"8/8/8/8/8/8/8/8 w - - 0 1\",\"computer_move\":\"b7a8q\",\"computer_action\":{\"move\":\"b7a8q\",\"replacement\":\"queen\",\"steps\":[\"Remove the opponent's piece from a8.\",\"Move your piece from b7 to a8.\",\"Replace the pawn on a8 with a queen of the same color.\",\"Confirm the replacement below after placing it.\"]}}");
    const UiScreen populated[] = {UI_GAME, UI_DIAGNOSTICS, UI_INSTRUCTIONS};
    for(unsigned i = 0; i < sizeof(populated)/sizeof(populated[0]); ++i) {
        scb_ui_show(populated[i]);
        lv_refr_now(NULL);
        if(!label_bounds(root())) return false;
    }
    puts("PASS: SQLite player creation, validation, rename, reopen, selection, delete confirmation and page bounds.");
    return true;
}

/* Full native-widget exercise against a separately started, isolated test service. */
static bool wait_json(const char *document, const char *path, const char *expected) {
    uint32_t started = lv_tick_get();
    while((uint32_t)(lv_tick_get() - started) < 8000) {
        scb_ui_tick();
        lv_timer_handler();
        char value[128];
        if(ui_json_text(&bridge, document, path, value, sizeof(value)) && !strcmp(value, expected)) return true;
        struct timespec delay = {0, 5000000};
        nanosleep(&delay, NULL);
    }
    fprintf(stderr, "Service UI test timed out: %s=%s. State: %s\n", path, expected, bridge.state);
    return false;
}
bool scb_ui_service_test(void) {
    if(!wait_json(bridge.state, "$.type", "state")) return false;
    if(!press("players") || !press("create-player")) return false;
    lv_textarea_set_text(name_input, "Alpha integration");
    if(!press("save-player") || !press("create-player")) return false;
    lv_textarea_set_text(name_input, "Beta integration");
    if(!press("save-player") || !press("use-player")) return false;
    if(!press("choose-black") || !press("select-player") || !press("use-player")) return false;
    if(!press("clock-none") || !press("prepare") || current != UI_BOARD_SETUP) return false;
    if(!wait_json(bridge.state, "$.ports[0].description", "Configured board port")) return false;
    if(!press("connect-board") || !wait_json(bridge.state, "$.board_known", "1")) return false;
    /* A periodic scan may still be completing, so wait before requesting the check. */
    if(!wait_json(bridge.state, "$.usb_busy", "0") || !press("check-position")) return false;
    if(!wait_json(bridge.state, "$.ready", "1") || !press("verify-pieces") || !press("start-game")) return false;
    if(!wait_json(bridge.state, "$.active", "1") || current != UI_GAME) return false;
    if(!wait_json(bridge.state, "$.last_move", "e2e4")) return false;
    if(!press("view-position") || !wait_json(bridge.review, "$.move", "e2e4")) return false;
    if(!press("back") || current != UI_GAME) return false;
    if(!press("pause") || !wait_json(bridge.state, "$.paused", "1")) return false;
    /* 棋盘测试复用串口；进入、扫描和返回不更改已接受的对局。 */
    if(!press("back") || !press("diagnostics") || current != UI_DIAGNOSTICS) return false;
    if(!wait_json(bridge.state, "$.usb_busy", "0") || !press("scan-board")) return false;
    if(!wait_json(bridge.state, "$.scan_timing.frame_us", "10000")) return false;
    if(strcmp(lv_label_get_text(lv_obj_get_child(sensor_tiles[28], 0)), "O")) return false;
    if(strcmp(lv_label_get_text(lv_obj_get_child(sensor_tiles[12], 0)), "")) return false;
    if(!press("back") || !press("continue-game") || current != UI_GAME || !state_flag("$.paused")) return false;
    if(!press("game-guidance") || !wait_json(bridge.state, "$.guidance", "1")) return false;
    if(!press("game-guidance") || !wait_json(bridge.state, "$.guidance", "0")) return false;
    /* 已开始的对局仍可通过连接入口断开并重新连接，不重置时钟。 */
    if(!press("game-connection") || current != UI_BOARD_SETUP || !config.reconnecting) return false;
    if(!wait_json(bridge.state, "$.usb_busy", "0") || !press("connect-board")) return false;
    if(!wait_json(bridge.state, "$.board_connected", "0") || !wait_json(bridge.state, "$.usb_busy", "0")) return false;
    if(!press("connect-board") || !wait_json(bridge.state, "$.board_known", "1")) return false;
    if(!press("return-game") || current != UI_GAME || !state_flag("$.paused")) return false;
    /* Reconnection is not fault recovery: reset must be explicitly verified. */
    if(!press("back") || !press("diagnostics")) return false;
    if(!wait_json(bridge.state, "$.usb_busy", "0") || !press("reset-fault")) return false;
    if(!wait_json(bridge.state, "$.fault", "") || !state_flag("$.paused")) return false;
    if(!press("sensor-game") || current != UI_GAME) return false;
    if(!press("pause") || !wait_json(bridge.state, "$.paused", "0")) return false;
    if(!press("end") || !press("cancel-end") || !state_flag("$.active")) return false;
    if(!press("end") || !press("confirm-end")) return false;
    if(!wait_json(bridge.history, "$.total", "1") || current != UI_HISTORY) return false;
    if(!press("review-game") || !wait_json(bridge.review, "$.total", "1")) return false;
    if(!press("next-move") || !wait_json(bridge.review, "$.move", "e2e4")) return false;
    if(!press("previous-move") || !wait_json(bridge.review, "$.ply", "0")) return false;
    if(!press("back") || current != UI_HISTORY || !press("back") || current != UI_HOME) return false;
    puts("PASS: native UI -> Unix socket -> real rules/SQLite -> emulated serial -> accepted move -> saved replay.");
    return true;
}
