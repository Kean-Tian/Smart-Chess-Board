#ifndef SCB_PLAYER_STORE_H
#define SCB_PLAYER_STORE_H
#include <stdbool.h>
#include <stdint.h>

#define SCB_PLAYER_NAME_MAX 24
#define SCB_PLAYER_PAGE_SIZE 4
struct sqlite3;
typedef struct {
    int64_t id;
    char name[SCB_PLAYER_NAME_MAX + 1];
} ScbPlayer;
typedef struct {
    struct sqlite3 *db;
    char path[4096];
    char error[192];
} PlayerStore;

/* No seed players: all names and the current selection come from SQLite. */
bool player_store_open(PlayerStore *store, const char *path);
void player_store_close(PlayerStore *store);
bool player_store_page(PlayerStore *store, int offset, ScbPlayer *rows, int *count, int *total);
bool player_store_selected(PlayerStore *store, ScbPlayer *player);
bool player_store_get(PlayerStore *store, int64_t id, ScbPlayer *player);
bool player_store_select(PlayerStore *store, int64_t id);
bool player_store_create(PlayerStore *store, const char *name);
bool player_store_rename(PlayerStore *store, int64_t id, const char *name);
bool player_store_delete(PlayerStore *store, int64_t id);
#endif
