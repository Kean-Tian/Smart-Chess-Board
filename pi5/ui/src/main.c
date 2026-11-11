/* Pi 5 display host: native LVGL rendering, persistent players and SDL input. */
#include "scb_ui.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#ifndef SCB_UI_HEADLESS
#define SDL_MAIN_HANDLED
#include <SDL.h>
#endif

static uint32_t framebuffer[SCB_UI_WIDTH * SCB_UI_HEIGHT];
static uint32_t draw_buffer[SCB_UI_WIDTH * SCB_UI_HEIGHT];
static lv_display_t *display;
static bool pixels_dirty;
static char temporary_directory[] = "/tmp/scb-ui-XXXXXX";
static bool temporary_database;
static void cleanup(void) {
    scb_ui_shutdown();
    if(temporary_database) {
        const char *files[] = {"players.sqlite3", "players.sqlite3-journal", "players.sqlite3-wal", "players.sqlite3-shm"};
        for(unsigned i = 0; i < sizeof(files) / sizeof(files[0]); ++i) {
            char path[4096];
            snprintf(path, sizeof(path), "%s/%s", temporary_directory, files[i]);
            unlink(path);
        }
        rmdir(temporary_directory);
    }
}
static uint32_t tick_ms(void) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (uint32_t)((uint64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000);
}
static void flush_pixels(lv_display_t *d, const lv_area_t *area, uint8_t *pixels) {
    int width = area->x2 - area->x1 + 1;
    for(int y = area->y1; y <= area->y2; ++y)
        memcpy(framebuffer + y * SCB_UI_WIDTH + area->x1,
               pixels + (y - area->y1) * width * 4, (size_t)width * 4);
    pixels_dirty = true;
    lv_display_flush_ready(d);
}
static bool save_ppm(const char *path) {
    lv_refr_now(display);
    FILE *f = fopen(path, "wb");
    if(!f) { perror(path); return false; }
    fprintf(f, "P6\n%d %d\n255\n", SCB_UI_WIDTH, SCB_UI_HEIGHT);
    for(size_t i = 0; i < SCB_UI_WIDTH * SCB_UI_HEIGHT; ++i) {
        uint32_t p = framebuffer[i];
        const unsigned char rgb[] = {(p >> 16) & 255, (p >> 8) & 255, p & 255};
        if(fwrite(rgb, 1, 3, f) != 3) { fclose(f); return false; }
    }
    return fclose(f) == 0;
}

#ifndef SCB_UI_HEADLESS
static bool pressed;
static int pointer_x, pointer_y;
static void read_pointer(lv_indev_t *input, lv_indev_data_t *data) {
    (void)input;
    data->point.x = pointer_x; data->point.y = pointer_y;
    data->state = pressed ? LV_INDEV_STATE_PRESSED : LV_INDEV_STATE_RELEASED;
}
static void handle_pointer_event(lv_indev_t *input, const SDL_Event *event) {
    if(event->type == SDL_MOUSEMOTION) {
        /* SDL_RenderSetLogicalSize already maps mouse events to UI coordinates. */
        pointer_x = event->motion.x;
        pointer_y = event->motion.y;
    } else if(event->type == SDL_MOUSEBUTTONDOWN || event->type == SDL_MOUSEBUTTONUP) {
        if(event->button.button != SDL_BUTTON_LEFT) return;
        pointer_x = event->button.x;
        pointer_y = event->button.y;
        pressed = event->type == SDL_MOUSEBUTTONDOWN;
    } else if(event->type == SDL_FINGERDOWN || event->type == SDL_FINGERMOTION || event->type == SDL_FINGERUP) {
        /* Touch events are already normalized to the logical viewport by SDL. */
        pointer_x = (int)(event->tfinger.x * (SCB_UI_WIDTH - 1));
        pointer_y = (int)(event->tfinger.y * (SCB_UI_HEIGHT - 1));
        pressed = event->type != SDL_FINGERUP;
    } else {
        return;
    }
    /* Deliver every transition, including down/up received in the same poll batch. */
    lv_indev_read(input);
}
static bool has_label(lv_obj_t *parent, const char *value) {
    if(lv_obj_check_type(parent, &lv_label_class) && !strcmp(lv_label_get_text(parent), value)) return true;
    for(uint32_t i = 0; i < lv_obj_get_child_count(parent); ++i) {
        if(has_label(lv_obj_get_child(parent, i), value)) return true;
    }
    return false;
}
static bool test_pointer_click(SDL_Window *window, SDL_Renderer *renderer, lv_indev_t *input,
                               int x, int y, bool touch, const char *expected) {
    int wx, wy, w, h;
    SDL_RenderLogicalToWindow(renderer, (float)x, (float)y, &wx, &wy);
    SDL_GetWindowSize(window, &w, &h);
    /* Queue a complete quick click before polling, as can happen over Connect. */
    for(int i = 0; i < 2; ++i) {
        SDL_Event event;
        memset(&event, 0, sizeof(event));
        if(touch) {
            event.type = i ? SDL_FINGERUP : SDL_FINGERDOWN;
            event.tfinger.windowID = SDL_GetWindowID(window);
            event.tfinger.touchId = 1;
            event.tfinger.fingerId = 1;
            event.tfinger.x = (float)wx / w;
            event.tfinger.y = (float)wy / h;
        } else {
            event.type = i ? SDL_MOUSEBUTTONUP : SDL_MOUSEBUTTONDOWN;
            event.button.windowID = SDL_GetWindowID(window);
            event.button.button = SDL_BUTTON_LEFT;
            event.button.state = i ? SDL_RELEASED : SDL_PRESSED;
            event.button.x = wx;
            event.button.y = wy;
        }
        if(SDL_PushEvent(&event) != 1) return false;
    }
    SDL_Event event;
    while(SDL_PollEvent(&event)) handle_pointer_event(input, &event);
    if(!has_label(lv_screen_active(), expected)) {
        fprintf(stderr, "Pointer test failed (%s): expected %s\n", touch ? "touch" : "mouse", expected);
        return false;
    }
    return true;
}
static bool test_window_input(SDL_Window *window, SDL_Renderer *renderer, lv_indev_t *input) {
    const int sizes[][2] = {{1440, 900}, {432, 768}, {720, 1280}};
    for(unsigned s = 0; s < sizeof(sizes) / sizeof(sizes[0]); ++s) {
        SDL_SetWindowSize(window, sizes[s][0], sizes[s][1]);
        SDL_PumpEvents();
        SDL_FlushEvents(SDL_FIRSTEVENT, SDL_LASTEVENT);
        if(SDL_RenderSetLogicalSize(renderer, SCB_UI_WIDTH, SCB_UI_HEIGHT) != 0) return false;
        for(int touch = 0; touch < 2; ++touch) {
            scb_ui_show(UI_HOME);
            lv_refr_now(display);
            if(!test_pointer_click(window, renderer, input, 528, 400, touch != 0, "No players yet") ||
               !test_pointer_click(window, renderer, input, 360, 934, touch != 0, "PLAYER NAME") ||
               !test_pointer_click(window, renderer, input, 110, 735, touch != 0, "q") ||
               !test_pointer_click(window, renderer, input, 528, 1184, touch != 0, "No players yet") ||
               !test_pointer_click(window, renderer, input, 72, 128, touch != 0, "Smart Chess Board") ||
               !test_pointer_click(window, renderer, input, 192, 666, touch != 0, "History is not loaded") ||
               !test_pointer_click(window, renderer, input, 72, 128, touch != 0, "Smart Chess Board") ||
               !test_pointer_click(window, renderer, input, 528, 666, touch != 0, "Occupancy unavailable / no fresh scan") ||
               !test_pointer_click(window, renderer, input, 72, 128, touch != 0, "Smart Chess Board")) return false;
        }
    }
    puts("PASS: SDL mouse/touch quick clicks, player forms and back navigation at three window sizes.");
    return true;
}
static int run_window(bool fullscreen, bool input_test) {
    if(SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER) != 0) {
        fprintf(stderr, "SDL could not open a display: %s\nRun from the Pi desktop session.\n", SDL_GetError());
        return 1;
    }
    SDL_SetHint(SDL_HINT_TOUCH_MOUSE_EVENTS, "0");
    SDL_SetHint(SDL_HINT_MOUSE_TOUCH_EVENTS, "0");
    Uint32 flags = SDL_WINDOW_SHOWN | SDL_WINDOW_ALLOW_HIGHDPI;
    if(fullscreen) flags |= SDL_WINDOW_FULLSCREEN_DESKTOP;
    SDL_Window *window = SDL_CreateWindow("Smart Chess Board", SDL_WINDOWPOS_CENTERED,
        SDL_WINDOWPOS_CENTERED, fullscreen ? SCB_UI_WIDTH : 432, fullscreen ? SCB_UI_HEIGHT : 768, flags);
    if(!window) { fprintf(stderr, "%s\n", SDL_GetError()); SDL_Quit(); return 1; }
    SDL_Renderer *renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE);
    if(!renderer) { SDL_DestroyWindow(window); SDL_Quit(); return 1; }
    SDL_RenderSetLogicalSize(renderer, SCB_UI_WIDTH, SCB_UI_HEIGHT);
    SDL_Texture *texture = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888,
        SDL_TEXTUREACCESS_STREAMING, SCB_UI_WIDTH, SCB_UI_HEIGHT);
    if(!texture) { SDL_DestroyRenderer(renderer); SDL_DestroyWindow(window); SDL_Quit(); return 1; }
    lv_indev_t *input = lv_indev_create();
    lv_indev_set_type(input, LV_INDEV_TYPE_POINTER);
    lv_indev_set_read_cb(input, read_pointer);
    if(input_test) {
        bool ok = test_window_input(window, renderer, input);
        SDL_DestroyTexture(texture); SDL_DestroyRenderer(renderer); SDL_DestroyWindow(window); SDL_Quit();
        return ok ? 0 : 1;
    }
    SDL_StartTextInput();
    bool running = true;
    while(running) {
        SDL_Event event;
        while(SDL_PollEvent(&event)) {
            if(event.type == SDL_WINDOWEVENT) pixels_dirty = true;
            if(event.type == SDL_QUIT || (event.type == SDL_KEYDOWN && event.key.keysym.sym == SDLK_ESCAPE))
                running = false;
            if(event.type == SDL_TEXTINPUT) scb_ui_text_input(event.text.text);
            if(event.type == SDL_KEYDOWN) {
                if(event.key.keysym.sym == SDLK_BACKSPACE) scb_ui_backspace();
                else if(event.key.keysym.sym == SDLK_RETURN) scb_ui_submit();
                else if(event.key.keysym.sym == SDLK_v && (event.key.keysym.mod & (KMOD_CTRL | KMOD_GUI))) {
                    char *value = SDL_GetClipboardText();
                    if(value) { scb_ui_text_input(value); SDL_free(value); }
                }
            }
            handle_pointer_event(input, &event);
        }
        scb_ui_tick();
        lv_timer_handler();
        if(pixels_dirty) {
            SDL_UpdateTexture(texture, NULL, framebuffer, SCB_UI_WIDTH * 4);
            SDL_RenderClear(renderer); SDL_RenderCopy(renderer, texture, NULL, NULL); SDL_RenderPresent(renderer);
            pixels_dirty = false;
        }
        SDL_Delay(5);
    }
    SDL_StopTextInput();
    SDL_DestroyTexture(texture); SDL_DestroyRenderer(renderer); SDL_DestroyWindow(window); SDL_Quit();
    return 0;
}
#endif

int main(int argc, char **argv) {
    const char *snapshots = NULL;
    const char *database = NULL;
    bool smoke = false, fullscreen = false, input_test = false, service_test = false;
    for(int i = 1; i < argc; ++i) {
        if(!strcmp(argv[i], "--snapshots") && i + 1 < argc) snapshots = argv[++i];
        else if(!strcmp(argv[i], "--smoke-test")) smoke = true;
        else if(!strcmp(argv[i], "--input-test")) input_test = true;
        else if(!strcmp(argv[i], "--service-test")) service_test = true;
        else if(!strcmp(argv[i], "--database") && i + 1 < argc) database = argv[++i];
        else if(!strcmp(argv[i], "--fullscreen")) fullscreen = true;
        else { fprintf(stderr, "Usage: %s [--database PATH] [--fullscreen] [--snapshots DIR] [--smoke-test] [--input-test]\n", argv[0]); return 2; }
    }
    if(service_test && (!database || !getenv("SCB_UI_SOCKET"))) {
        fputs("Service tests require an explicit temporary database and socket.\n", stderr); return 2;
    }
    char test_path[4096];
    if(smoke || input_test || snapshots) {
        /* Verification must never insert fixtures into the user's real player database. */
        if(!mkdtemp(temporary_directory)) { perror("Temporary player database"); return 1; }
        temporary_database = true;
        setenv("SCB_UI_TEST_MODE", "1", 1);
        snprintf(test_path, sizeof(test_path), "%s/players.sqlite3", temporary_directory);
        database = test_path;
    }
    atexit(cleanup);
    lv_init(); lv_tick_set_cb(tick_ms);
    display = lv_display_create(SCB_UI_WIDTH, SCB_UI_HEIGHT);
    lv_display_set_color_format(display, LV_COLOR_FORMAT_XRGB8888);
    lv_display_set_buffers(display, draw_buffer, NULL, sizeof(draw_buffer), LV_DISPLAY_RENDER_MODE_FULL);
    lv_display_set_flush_cb(display, flush_pixels);
    scb_ui_init(database);
    if(smoke) return scb_ui_smoke_test() ? 0 : 1;
    if(service_test) return scb_ui_service_test() ? 0 : 1;
    if(snapshots) {
        if(mkdir(snapshots, 0755) != 0 && errno != EEXIST) { perror(snapshots); return 1; }
        char path[2048]; snprintf(path, sizeof(path), "%s/hotspots.json", snapshots);
        FILE *map = fopen(path, "w"); if(!map) return 1;
        fputs("{\"width\":720,\"height\":1280,\"screens\":{", map);
        for(int i = 0; i < UI_SCREEN_COUNT; ++i) {
            scb_ui_show((UiScreen)i);
            snprintf(path, sizeof(path), "%s/%s.ppm", snapshots, scb_ui_screen_name((UiScreen)i));
            if(!save_ppm(path)) { fclose(map); return 1; }
            if(i) fputc(',', map);
            fprintf(map, "\"%s\":", scb_ui_screen_name((UiScreen)i)); scb_ui_write_hotspots(map);
        }
        fputs("}}\n", map); fclose(map);
        puts("Rendered all portrait screens using the native LVGL UI."); return 0;
    }
#ifdef SCB_UI_HEADLESS
    (void)fullscreen;
    (void)input_test;
    fputs("Headless build: use --snapshots DIR or --smoke-test. Build with SDL2 for touch interaction.\n", stderr);
    return 2;
#else
    return run_window(fullscreen, input_test);
#endif
}
