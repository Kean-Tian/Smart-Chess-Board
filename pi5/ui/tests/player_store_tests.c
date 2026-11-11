/* Real SQLite file tests. Fixtures are isolated and never shipped as player data. */
#include "player_store.h"
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define CHECK(condition) do { if(!(condition)) { \
    fprintf(stderr, "Database test failed at line %d: %s (%s)\n", __LINE__, #condition, s.error); \
    result = 1; goto cleanup; } } while(0)

int main(void) {
    char dir[] = "/tmp/scb-player-tests-XXXXXX";
    if(!mkdtemp(dir)) return 1;
    char path[4096];
    snprintf(path, sizeof(path), "%s/players.sqlite3", dir);
    PlayerStore s = {0}, other = {0};
    ScbPlayer rows[SCB_PLAYER_PAGE_SIZE], selected;
    int count = 0, total = 0, result = 0;
    CHECK(player_store_open(&s, path));
    CHECK(player_store_page(&s, 0, rows, &count, &total) && !count && !total);
    CHECK(player_store_selected(&s, &selected) && !selected.id);
    CHECK(!player_store_create(&s, "   "));
    CHECK(!player_store_create(&s, "1234567890123456789012345"));
    CHECK(!player_store_create(&s, "bad\nname"));
    CHECK(!player_store_create(&s, "\xE7\x8E\x8B"));
    CHECK(player_store_create(&s, "  O'Neil  "));
    CHECK(player_store_selected(&s, &selected) && !strcmp(selected.name, "O'Neil"));
    int64_t first = selected.id;
    CHECK(!player_store_create(&s, "o'neil"));
    CHECK(player_store_selected(&s, &selected) && selected.id == first);
    CHECK(player_store_create(&s, "Second"));
    CHECK(player_store_selected(&s, &selected));
    int64_t second = selected.id;
    CHECK(!player_store_rename(&s, second, "O'NEIL"));
    CHECK(player_store_rename(&s, second, "Name');--"));
    CHECK(player_store_select(&s, first));
    CHECK(!player_store_select(&s, 999999));
    CHECK(player_store_selected(&s, &selected) && selected.id == first);
    player_store_close(&s);
    CHECK(player_store_open(&s, path));
    CHECK(player_store_selected(&s, &selected) && selected.id == first && !strcmp(selected.name, "O'Neil"));
    CHECK(player_store_page(&s, 0, rows, &count, &total) && total == 2);
    CHECK(!strcmp(rows[0].name, "Name');--"));
    for(int i = 0; i < 7; ++i) {
        char name[25];
        snprintf(name, sizeof(name), "Paged player %d", i);
        CHECK(player_store_create(&s, name));
    }
    CHECK(player_store_page(&s, 0, rows, &count, &total) && count == 4 && total == 9);
    int64_t last_page_one = rows[3].id;
    CHECK(player_store_page(&s, 4, rows, &count, &total) && count == 4 && rows[0].id != last_page_one);
    CHECK(player_store_page(&s, 8, rows, &count, &total) && count == 1);
    CHECK(player_store_open(&other, path));
    CHECK(sqlite3_exec(other.db, "BEGIN IMMEDIATE", NULL, NULL, NULL) == SQLITE_OK);
    CHECK(!player_store_create(&s, "Must not appear"));
    CHECK(sqlite3_exec(other.db, "ROLLBACK", NULL, NULL, NULL) == SQLITE_OK);
    player_store_close(&other);
    CHECK(player_store_page(&s, 0, rows, &count, &total) && total == 9);
    CHECK(player_store_select(&s, first));
    CHECK(player_store_delete(&s, second));
    CHECK(player_store_selected(&s, &selected) && selected.id == first);
    CHECK(player_store_delete(&s, first));
    CHECK(player_store_selected(&s, &selected) && !selected.id);
    CHECK(!player_store_delete(&s, first));
    CHECK(!player_store_rename(&s, first, "Missing"));
    player_store_close(&s);
    CHECK(player_store_open(&s, path));
    CHECK(player_store_selected(&s, &selected) && !selected.id);
    CHECK(player_store_page(&s, 0, rows, &count, &total) && total == 7);
    CHECK(sqlite3_exec(s.db, "PRAGMA user_version=3", NULL, NULL, NULL) == SQLITE_OK);
    player_store_close(&s);
    CHECK(!player_store_open(&s, path));
    CHECK(strstr(s.error, "newer") != NULL);
    CHECK(!player_store_open(&s, dir));
    puts("PASS: empty database, validation, prepared values, duplicates, persistence, pagination, locks and selection integrity.");
cleanup:
    player_store_close(&other);
    player_store_close(&s);
    unlink(path);
    rmdir(dir);
    return result;
}
