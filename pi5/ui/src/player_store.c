/* SQLite persistence for the native Pi UI. This module creates no sample data. */
#include "player_store.h"
#include "storage_schema.h"
#include <sqlite3.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <sys/stat.h>

static bool fail(PlayerStore *s, const char *message) {
    snprintf(s->error, sizeof(s->error), "%s", message);
    return false;
}
static bool db_error(PlayerStore *s) {
    int code = sqlite3_errcode(s->db);
    if(code == SQLITE_BUSY || code == SQLITE_LOCKED)
        return fail(s, "Player database is busy. Please try again.");
    if(code == SQLITE_CONSTRAINT) {
        if(sqlite3_extended_errcode(s->db) == SQLITE_CONSTRAINT_UNIQUE)
            return fail(s, "That player name already exists.");
        return fail(s, "Player data changed. Refresh and try again.");
    }
    return fail(s, sqlite3_errmsg(s->db));
}
static bool ready(PlayerStore *s) {
    return s->db != NULL || fail(s, "Player database is unavailable.");
}
static bool exec_sql(PlayerStore *s, const char *sql) {
    return sqlite3_exec(s->db, sql, NULL, NULL, NULL) == SQLITE_OK || db_error(s);
}
static bool prepare(PlayerStore *s, sqlite3_stmt **stmt, const char *sql) {
    /* 先准备 SQL，再绑定参数，避免把玩家名字拼接成 SQL 代码。 */
    return ready(s) && (sqlite3_prepare_v2(s->db, sql, -1, stmt, NULL) == SQLITE_OK || db_error(s));
}
static bool finish_write(PlayerStore *s, sqlite3_stmt *stmt, bool require_row) {
    /* 执行写入并释放语句；需要时确认确实修改了一条玩家记录。 */
    bool ok = sqlite3_step(stmt) == SQLITE_DONE;
    if(!ok) db_error(s);
    else if(require_row && sqlite3_changes(s->db) != 1)
        ok = fail(s, "This player no longer exists. Refresh and try again.");
    sqlite3_finalize(stmt);
    return ok;
}
static bool make_parent(PlayerStore *s) {
    char parent[sizeof(s->path)];
    snprintf(parent, sizeof(parent), "%s", s->path);
    char *last = strrchr(parent, '/');
    if(!last) return true;
    *last = '\0';
    for(char *p = parent + 1; ; ++p) {
        if(*p != '/' && *p != '\0') continue;
        char saved = *p;
        *p = '\0';
        if(parent[0] && mkdir(parent, 0700) != 0 && errno != EEXIST)
            return fail(s, "Cannot create the player database directory.");
        *p = saved;
        if(!saved) break;
    }
    return true;
}
bool player_store_open(PlayerStore *s, const char *path) {
    /* 优先使用指定路径，否则打开用户目录中的持久数据库。 */
    memset(s, 0, sizeof(*s));
    if(!path || !*path) path = getenv("SCB_PLAYER_DB");
    if(path && *path) {
        if(strlen(path) >= sizeof(s->path)) return fail(s, "Player database path is too long.");
        snprintf(s->path, sizeof(s->path), "%s", path);
    } else {
        const char *base = getenv("XDG_DATA_HOME");
        const char *home = getenv("HOME");
        int n;
        if(base && *base) n = snprintf(s->path, sizeof(s->path), "%s/scb/players.sqlite3", base);
        else if(home && *home) n = snprintf(s->path, sizeof(s->path), "%s/.local/share/scb/players.sqlite3", home);
        else return fail(s, "HOME is unset. Set SCB_PLAYER_DB to a writable path.");
        if(n < 0 || (size_t)n >= sizeof(s->path)) return fail(s, "Player database path is too long.");
    }
    if(strcmp(s->path, ":memory:") && !make_parent(s)) return false;
    if(sqlite3_open_v2(s->path, &s->db, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, NULL) != SQLITE_OK) {
        fail(s, s->db ? sqlite3_errmsg(s->db) : "Could not open the player database.");
        player_store_close(s);
        return false;
    }
    /* 其他连接正在写入时短暂等待；仍被占用就返回错误。 */
    sqlite3_busy_timeout(s->db, 250);
    sqlite3_stmt *stmt = NULL;
    if(!prepare(s, &stmt, "PRAGMA user_version")) goto error;
    int rc = sqlite3_step(stmt);
    int version = rc == SQLITE_ROW ? sqlite3_column_int(stmt, 0) : -1;
    sqlite3_finalize(stmt);
    if(version < 0) { db_error(s); goto error; }
    if(version > 2) { fail(s, "This player database needs a newer application version."); goto error; }
    /* 使用与 Python 共用的表结构；已有表和已有玩家不会被清空。 */
    if(!exec_sql(s, scb_schema_sql)) goto error;
    return true;
error:
    sqlite3_exec(s->db, "ROLLBACK", NULL, NULL, NULL);
    player_store_close(s);
    return false;
}
void player_store_close(PlayerStore *s) {
    if(s->db) sqlite3_close(s->db);
    s->db = NULL;
}
bool player_store_page(PlayerStore *s, int offset, ScbPlayer *rows, int *count, int *total) {
    /* 先查询总人数，再按名字取一页；offset 是跳过的记录数。 */
    *count = *total = 0;
    sqlite3_stmt *stmt = NULL;
    if(offset < 0 || !prepare(s, &stmt, "SELECT count(*) FROM players")) return false;
    int rc = sqlite3_step(stmt);
    if(rc != SQLITE_ROW) { db_error(s); sqlite3_finalize(stmt); return false; }
    sqlite3_int64 size = sqlite3_column_int64(stmt, 0);
    *total = size > INT_MAX ? INT_MAX : (int)size;
    sqlite3_finalize(stmt);
    if(!prepare(s, &stmt, "SELECT id,name FROM players ORDER BY name COLLATE NOCASE,id LIMIT ? OFFSET ?")) return false;
    sqlite3_bind_int(stmt, 1, SCB_PLAYER_PAGE_SIZE);
    sqlite3_bind_int(stmt, 2, offset);
    while((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
        ScbPlayer *row = &rows[(*count)++];
        row->id = sqlite3_column_int64(stmt, 0);
        snprintf(row->name, sizeof(row->name), "%s", (const char *)sqlite3_column_text(stmt, 1));
    }
    if(rc != SQLITE_DONE) db_error(s);
    sqlite3_finalize(stmt);
    return rc == SQLITE_DONE;
}
bool player_store_selected(PlayerStore *s, ScbPlayer *player) {
    /* 将当前选择与玩家表关联；没有选择时返回空玩家。 */
    memset(player, 0, sizeof(*player));
    sqlite3_stmt *stmt = NULL;
    if(!prepare(s, &stmt, "SELECT p.id,p.name FROM ui_state u LEFT JOIN players p ON p.id=u.selected_player_id WHERE u.id=1")) return false;
    int rc = sqlite3_step(stmt);
    if(rc == SQLITE_ROW && sqlite3_column_type(stmt, 0) != SQLITE_NULL) {
        player->id = sqlite3_column_int64(stmt, 0);
        snprintf(player->name, sizeof(player->name), "%s", (const char *)sqlite3_column_text(stmt, 1));
    } else if(rc != SQLITE_ROW) db_error(s);
    sqlite3_finalize(stmt);
    return rc == SQLITE_ROW;
}
bool player_store_select(PlayerStore *s, int64_t id) {
    /* 保存的是玩家 ID；id 为 0 时把选择设为 NULL。 */
    sqlite3_stmt *stmt = NULL;
    if(!prepare(s, &stmt, "UPDATE ui_state SET selected_player_id=? WHERE id=1")) return false;
    if(id) sqlite3_bind_int64(stmt, 1, id);
    else sqlite3_bind_null(stmt, 1);
    return finish_write(s, stmt, true);
}
bool player_store_get(PlayerStore *s, int64_t id, ScbPlayer *player) {
    /* 按固定 ID 读取玩家，改名不会改变这个身份编号。 */
    memset(player, 0, sizeof(*player));
    sqlite3_stmt *stmt = NULL;
    if(!prepare(s, &stmt, "SELECT id,name FROM players WHERE id=?")) return false;
    sqlite3_bind_int64(stmt, 1, id);
    int rc = sqlite3_step(stmt);
    if(rc == SQLITE_ROW) {
        player->id = sqlite3_column_int64(stmt, 0);
        snprintf(player->name, sizeof(player->name), "%s", (const char *)sqlite3_column_text(stmt, 1));
    }
    sqlite3_finalize(stmt);
    return rc == SQLITE_ROW;
}
static bool normalize_name(PlayerStore *s, const char *name, char normalized[SCB_PLAYER_NAME_MAX + 1]) {
    /* 去掉首尾空格，检查长度和当前字体可显示的字符。 */
    if(!name) return fail(s, "Enter a player name.");
    while(*name == ' ') ++name;
    size_t n = strlen(name);
    while(n && name[n - 1] == ' ') --n;
    if(!n) return fail(s, "Enter a player name.");
    if(n > SCB_PLAYER_NAME_MAX) return fail(s, "Use at most 24 characters.");
    for(size_t i = 0; i < n; ++i) {
        /* The bundled font covers printable ASCII; reject names it cannot display. */
        if((unsigned char)name[i] < 32 || (unsigned char)name[i] > 126)
            return fail(s, "Use English letters, numbers, spaces or punctuation.");
    }
    memcpy(normalized, name, n);
    normalized[n] = '\0';
    return true;
}
bool player_store_create(PlayerStore *s, const char *name) {
    /* 新增玩家并自动选中：两项放在同一事务里，失败就一起撤销。 */
    char normalized[SCB_PLAYER_NAME_MAX + 1];
    if(!ready(s) || !normalize_name(s, name, normalized) || !exec_sql(s, "BEGIN IMMEDIATE")) return false;
    sqlite3_stmt *stmt = NULL;
    bool ok = prepare(s, &stmt, "INSERT INTO players(name) VALUES(?)");
    if(ok) {
        sqlite3_bind_text(stmt, 1, normalized, -1, SQLITE_TRANSIENT);
        ok = finish_write(s, stmt, true);
    }
    if(ok) ok = player_store_select(s, sqlite3_last_insert_rowid(s->db));
    if(ok) ok = exec_sql(s, "COMMIT");
    if(!ok) sqlite3_exec(s->db, "ROLLBACK", NULL, NULL, NULL);
    return ok;
}
bool player_store_rename(PlayerStore *s, int64_t id, const char *name) {
    /* 只修改名字和更新时间，保留玩家 ID。 */
    char normalized[SCB_PLAYER_NAME_MAX + 1];
    if(!ready(s) || !normalize_name(s, name, normalized)) return false;
    sqlite3_stmt *stmt = NULL;
    if(!prepare(s, &stmt, "UPDATE players SET name=?,updated_at=CURRENT_TIMESTAMP WHERE id=?")) return false;
    sqlite3_bind_text(stmt, 1, normalized, -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt, 2, id);
    return finish_write(s, stmt, true);
}
bool player_store_delete(PlayerStore *s, int64_t id) {
    /* 外键负责清空当前选择和对局中的玩家关联，历史名字仍保留。 */
    sqlite3_stmt *stmt = NULL;
    if(!prepare(s, &stmt, "DELETE FROM players WHERE id=?")) return false;
    sqlite3_bind_int64(stmt, 1, id);
    return finish_write(s, stmt, true);
}
