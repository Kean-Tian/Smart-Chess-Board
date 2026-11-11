#ifndef SCB_UI_BRIDGE_H
#define SCB_UI_BRIDGE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
struct sqlite3;
struct sqlite3_stmt;
#define SCB_BRIDGE_STATE 1U
#define SCB_BRIDGE_HISTORY 2U
#define SCB_BRIDGE_REVIEW 4U
#define SCB_BRIDGE_CONNECTION 8U

typedef struct {
    int fd;
    bool disabled, connecting, connected;
    uint32_t last_attempt, last_state;
    char path[104], error[192];
    char incoming[32768], outgoing[8192];
    size_t incoming_size, outgoing_size;
    char state[16384], history[8192], review[4096];
    struct sqlite3 *json;
    struct sqlite3_stmt *extract;
} UiBridge;

bool ui_bridge_init(UiBridge *bridge, bool disabled);
void ui_bridge_close(UiBridge *bridge);
unsigned ui_bridge_poll(UiBridge *bridge, uint32_t now);
bool ui_bridge_send(UiBridge *bridge, const char *format, ...);
bool ui_json_text(UiBridge *bridge, const char *document, const char *path, char *out, size_t capacity);
int64_t ui_json_int(UiBridge *bridge, const char *document, const char *path, int64_t fallback);
bool ui_json_quote(UiBridge *bridge, const char *value, char *out, size_t capacity);
#endif
