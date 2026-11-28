/* Diagnostic pages share the native shell, buttons, bridge and board orientation.
 * Pixels are acknowledged commands, never measurements of physical illumination. */
static void label_value(lv_obj_t *label, const char *value);
static bool is_led_page(UiScreen screen) {
    return screen == UI_LED_AUTO || screen == UI_LED_MANUAL || screen == UI_LED_CURRENT;
}
static void led_widgets_reset(void) {
    memset(led_tiles, 0, sizeof(led_tiles));
    memset(led_controls, 0, sizeof(led_controls));
    memset(led_entry, 0, sizeof(led_entry));
    led_summary = led_message = NULL;
}
static void board_test_menu(void) {
    shell("Board Test", "Connect the board through Sensor Test before using LEDs.");
    led_widgets_reset();
    button(root(), "Sensor Test", 32, 300, 656, 104, true, "sensor-test", A_NAV, UI_DIAGNOSTICS, "diagnostics");
    button(root(), "LED Test", 32, 440, 656, 104, false, "led-test", A_NAV, UI_LED_TEST, "led-test");
    text(root(), "Sensor Test keeps its existing mapping and live occupancy view.\n\nLED diagnostics require an idle board and no active or paused game.", 32, 600, 656, 28, MUTED);
}
static void led_test_menu(void) {
    shell("LED Test", "Diagnostic commands use the existing board connection.");
    led_widgets_reset();
    const char *titles[] = {"Automatic RGB Test", "Manual LED Test", "Current Limit Test"};
    const char *ids[] = {"led-auto", "led-manual", "led-current"};
    for(int i = 0; i < 3; ++i)
        led_entry[i] = button(root(), titles[i], 32, 300+i*140, 656, 104, i == 0, ids[i], A_LED_OPEN, i, NULL);
    led_message = text(root(), "", 32, 790, 656, 28, MUTED);
    text(root(), "Command acknowledgements do not verify light or current.\n\nAll RGB channels stay within the existing 32/255 limit. No motor commands are issued.", 32, 1000, 656, 24, MUTED);
}
static void led_board(int y, bool interactive) {
    /* Same orientation as draw_position: a8 top-left, a1 bottom-left.
     * Protocol squares are logical coordinates; firmware handles strip serpentine. */
    for(int row = 0; row < 8; ++row) for(int col = 0; col < 8; ++col) {
        int index = (7-row)*8+col;
        char square[3] = {(char)('a'+col), (char)('8'-row), 0};
        led_tiles[index] = button(root(), square, 112+col*62, y+row*62, 60, 60, false,
                                 "", interactive ? A_LED_SQUARE : A_NONE, index, NULL);
        lv_obj_set_style_radius(led_tiles[index], 4, 0);
        lv_obj_set_style_text_font(led_tiles[index], font(20), 0);
    }
}
static void led_test_page(void) {
    const char *title = current == UI_LED_AUTO ? "Automatic RGB Test" : current == UI_LED_MANUAL ? "Manual LED Test" : "Current Limit Test";
    shell(title, "Commanded LED states; physical verification is required.");
    led_widgets_reset();
    if(current == UI_LED_AUTO) {
        led_summary = text(root(), "", 32, 260, 656, 24, INK);
        led_board(416, false);
        const char *titles[] = {"Start", "Pause", "Resume", "Stop", "Restart"};
        const char *ids[] = {"led-start", "led-pause", "led-resume", "led-stop", "led-restart"};
        Action actions[] = {A_LED_START, A_LED_PAUSE, A_LED_RESUME, A_LED_STOP, A_LED_RESTART};
        for(int i = 0; i < 5; ++i)
            led_controls[i] = button(root(), titles[i], 32+(i<3 ? i*224 : (i-3)*336), i<3 ? 952 : 1048,
                                     i<3 ? 208 : 320, 80, i==0, ids[i], actions[i], 0, NULL);
        led_message = text(root(), "", 32, 1150, 656, 20, MUTED);
    } else if(current == UI_LED_MANUAL) {
        const char *names[] = {"Red", "Green", "Blue", "White", "Off"};
        for(int i = 0; i < 5; ++i)
            led_controls[i] = button(root(), names[i], 32+i*134, 268, 120, 80, false, "", A_LED_COLOR, i, NULL);
        led_board(400, true);
        led_controls[5] = button(root(), "Clear All LEDs", 32, 940, 656, 80, true, "led-clear", A_LED_CLEAR, 0, NULL);
        led_summary = text(root(), "", 32, 1040, 656, 24, INK);
        led_message = text(root(), "", 32, 1160, 656, 20, MUTED);
    } else {
        text(root(), "Required: average array current <= 2.0 A\nover ANY one-second interval.\nExternal time-resolved measurement required.", 32, 260, 656, 24, RED);
        const char *names[] = {"Max Load", "All Red", "All Green", "All Blue", "All White", "Transitions"};
        for(int i = 0; i < 6; ++i)
            led_controls[i] = button(root(), names[i], 32+(i%3)*224, 416+(i/3)*100, 208, 80, false, "", A_LED_PATTERN, i, NULL);
        led_summary = text(root(), "", 32, 660, 656, 28, INK);
        led_controls[6] = button(root(), "Clear All LEDs", 32, 932, 320, 88, false, "led-clear", A_LED_CLEAR, 0, NULL);
        led_controls[7] = button(root(), "Stop Test", 368, 932, 320, 88, true, "led-stop", A_LED_STOP, 0, NULL);
        led_message = text(root(), "", 32, 1060, 656, 24, MUTED);
    }
    /* Bound long backend error strings without pushing controls off-screen. */
    lv_obj_set_height(led_message, current == UI_LED_CURRENT ? 180 : 110);
    lv_label_set_long_mode(led_message, LV_LABEL_LONG_DOT);
}
static void refresh_led_page(void) {
    bool connected = service_online() && state_flag("$.board_connected");
    bool blocked = !connected || state_flag("$.active") || state_flag("$.paused") || state_flag("$.led_diagnostics.owned");
    char phase[40], message[512], square[8], color[32], pattern[40], pixels[80], value[512], fault[100];
    ui_json_text(&bridge, bridge.state, "$.fault", fault, sizeof(fault));
    ui_json_text(&bridge, bridge.state, "$.led_diagnostics.phase", phase, sizeof(phase));
    ui_json_text(&bridge, bridge.state, "$.led_diagnostics.message", message, sizeof(message));
    if(current == UI_LED_TEST) {
        for(int i=0; i<3; ++i) disable(led_entry[i], blocked || fault[0]);
        label_value(led_message, !connected ? "Connect the board in Sensor Test first." : blocked ? "Finish the active/paused game or pending LED clear first." : fault[0] ? "Resolve the board fault in Sensor Test first." : "Board connected. Choose a diagnostic page.");
        return;
    }
    if(!is_led_page(current)) return;
    ui_json_text(&bridge, bridge.state, "$.led_diagnostics.square", square, sizeof(square));
    ui_json_text(&bridge, bridge.state, "$.led_diagnostics.color", color, sizeof(color));
    ui_json_text(&bridge, bridge.state, "$.led_diagnostics.pattern", pattern, sizeof(pattern));
    ui_json_text(&bridge, bridge.state, "$.led_diagnostics.pixels", pixels, sizeof(pixels));
    bool owned = state_flag("$.led_diagnostics.owned"), closing = state_flag("$.led_diagnostics.closing");
    bool ready = connected && owned && !closing && state_flag("$.led_diagnostics.known") && strcmp(phase, "error");
    int active = (int)ui_json_int(&bridge, bridge.state, "$.led_diagnostics.active_leds", 0);
    if(current == UI_LED_CURRENT) {
        snprintf(value, sizeof(value), "Pattern: %s\nCommanded active LEDs: %d / 64\nRGB: %lld, %lld, %lld (max 32/255)\nElapsed: %.1f s\nCurrent: NOT MEASURED", pattern, active,
                 (long long)ui_json_int(&bridge, bridge.state, "$.led_diagnostics.rgb[0]", 0),
                 (long long)ui_json_int(&bridge, bridge.state, "$.led_diagnostics.rgb[1]", 0),
                 (long long)ui_json_int(&bridge, bridge.state, "$.led_diagnostics.rgb[2]", 0),
                 ui_json_int(&bridge, bridge.state, "$.led_diagnostics.elapsed_ms", 0)/1000.0);
        for(int i=0; i<6; ++i) disable(led_controls[i], !ready);
        for(int i=6; i<8; ++i) disable(led_controls[i], !connected || !owned || closing);
    } else {
        static const char *choices[] = {"red", "green", "blue", "white", "off"};
        snprintf(value, sizeof(value), "Square: %s  Color: %s\nCommanded active LEDs: %d   State: %s\n%s: %lld / 64", square,
                 current == UI_LED_MANUAL ? choices[led_color_choice] : color, active, phase, "Completed squares",
                 (long long)ui_json_int(&bridge, bridge.state, "$.led_diagnostics.progress", 0));
        for(int i=0; i<64; ++i) if(led_tiles[i]) {
            char p = strlen(pixels)==64 ? pixels[i] : '?';
            uint32_t fill = p=='R' ? 0xCC4030 : p=='G' ? 0x34804C : p=='B' ? 0x4068CC : p=='W' ? PAPER : p=='.' ? ((i/8+i%8)%2 ? SOFT : 0xDED9CB) : 0xB6B6B6;
            lv_obj_set_style_bg_color(led_tiles[i], lv_color_hex(fill), 0);
            lv_obj_set_style_text_color(led_tiles[i], lv_color_hex(p=='R'||p=='G'||p=='B' ? PAPER : INK), 0);
            if(current == UI_LED_MANUAL) disable(led_tiles[i], !ready);
        }
        if(current == UI_LED_AUTO) {
            bool running = state_flag("$.led_diagnostics.running"), paused = state_flag("$.led_diagnostics.paused");
            disable(led_controls[0], !ready || running);
            disable(led_controls[1], !ready || !running || paused);
            disable(led_controls[2], !ready || !paused);
            disable(led_controls[3], !connected || !owned || closing);
            disable(led_controls[4], !ready);
        } else {
            for(int i=0; i<5; ++i) {
                disable(led_controls[i], !ready);
                lv_obj_set_style_border_width(led_controls[i], i==led_color_choice ? 3 : 0, 0);
                lv_obj_set_style_border_color(led_controls[i], lv_color_hex(GOLD), 0);
            }
            disable(led_controls[5], !connected || !owned || closing);
        }
    }
    label_value(led_summary, value);
    label_value(led_message, !connected ? "Disconnected. Sequence stopped; physical LED state unknown. Reconnect through Sensor Test to clear." : local_notice[0] ? local_notice : message);
}
