/* Nonblocking local IPC. JSON is decoded by the existing SQLite JSON extension. */
#include "ui_bridge.h"
#include <sqlite3.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

static void disconnect(UiBridge *b) {
    if(b->fd >= 0) close(b->fd);
    b->fd = -1;
    b->connected = b->connecting = false;
    b->incoming_size = b->outgoing_size = 0;
}
static bool extract(UiBridge *b, const char *document, const char *path) {
    if(!b->extract || !document || !*document) return false;
    sqlite3_reset(b->extract);
    sqlite3_clear_bindings(b->extract);
    sqlite3_bind_text(b->extract, 1, document, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(b->extract, 2, path, -1, SQLITE_TRANSIENT);
    return sqlite3_step(b->extract) == SQLITE_ROW && sqlite3_column_type(b->extract, 0) != SQLITE_NULL;
}
bool ui_json_text(UiBridge *b, const char *document, const char *path, char *out, size_t capacity) {
    if(!capacity) return false;
    out[0] = '\0';
    if(!extract(b, document, path)) return false;
    const unsigned char *value = sqlite3_column_text(b->extract, 0);
    if(!value || strlen((const char *)value) >= capacity) return false;
    snprintf(out, capacity, "%s", (const char *)value);
    return true;
}
int64_t ui_json_int(UiBridge *b, const char *document, const char *path, int64_t fallback) {
    if(!extract(b, document, path)) return fallback;
    return sqlite3_column_int64(b->extract, 0);
}
bool ui_json_quote(UiBridge *b, const char *value, char *out, size_t capacity) {
    sqlite3_stmt *stmt = NULL;
    if(!b->json || sqlite3_prepare_v2(b->json, "SELECT json_quote(?)", -1, &stmt, NULL) != SQLITE_OK) return false;
    sqlite3_bind_text(stmt, 1, value, -1, SQLITE_TRANSIENT);
    bool ok = sqlite3_step(stmt) == SQLITE_ROW;
    if(ok) {
        const char *quoted = (const char *)sqlite3_column_text(stmt, 0);
        ok = quoted && strlen(quoted) < capacity;
        if(ok) snprintf(out, capacity, "%s", quoted);
    }
    sqlite3_finalize(stmt);
    return ok;
}
bool ui_bridge_init(UiBridge *b, bool disabled) {
    memset(b, 0, sizeof(*b));
    b->fd = -1;
    b->disabled = disabled;
    if(sqlite3_open(":memory:", &b->json) != SQLITE_OK ||
       sqlite3_prepare_v2(b->json, "SELECT json_extract(?1,?2)", -1, &b->extract, NULL) != SQLITE_OK) {
        snprintf(b->error, sizeof(b->error), "SQLite JSON support is required.");
        return false;
    }
    const char *path = getenv("SCB_UI_SOCKET");
    char fallback[4096];
    if(!path || !*path) {
        const char *runtime = getenv("XDG_RUNTIME_DIR");
        const char *home = getenv("HOME");
        if(runtime && *runtime) snprintf(fallback, sizeof(fallback), "%s/scb-ui.sock", runtime);
        else if(home && *home) snprintf(fallback, sizeof(fallback), "%s/.local/share/scb/scb-ui.sock", home);
        else snprintf(fallback, sizeof(fallback), "/tmp/scb-no-service.sock");
        path = fallback;
    }
    if(strlen(path) >= sizeof(b->path)) {
        snprintf(b->error, sizeof(b->error), "Local service socket path is too long.");
        return false;
    }
    snprintf(b->path, sizeof(b->path), "%s", path);
    b->last_attempt = (uint32_t)-1000;
    return true;
}
void ui_bridge_close(UiBridge *b) {
    disconnect(b);
    if(b->extract) sqlite3_finalize(b->extract);
    if(b->json) sqlite3_close(b->json);
    b->extract = NULL;
    b->json = NULL;
}
bool ui_bridge_send(UiBridge *b, const char *format, ...) {
    if(!b->connected) {
        snprintf(b->error, sizeof(b->error), "Game service unavailable. Start the UI with pi5/start.sh ui.");
        return false;
    }
    char message[1024];
    va_list arguments;
    va_start(arguments, format);
    int n = vsnprintf(message, sizeof(message), format, arguments);
    va_end(arguments);
    if(n < 0 || (size_t)n >= sizeof(message) || b->outgoing_size + (size_t)n + 1 > sizeof(b->outgoing)) {
        snprintf(b->error, sizeof(b->error), "UI command queue is full. Please try again.");
        return false;
    }
    memcpy(b->outgoing + b->outgoing_size, message, (size_t)n);
    b->outgoing_size += (size_t)n;
    b->outgoing[b->outgoing_size++] = '\n';
    return true;
}
static unsigned accept_line(UiBridge *b, char *line, uint32_t now) {
    char kind[32];
    if(!ui_json_text(b, line, "$.type", kind, sizeof(kind))) return 0;
    char *destination = NULL;
    size_t capacity = 0;
    unsigned change = 0;
    if(!strcmp(kind, "state")) {
        destination = b->state; capacity = sizeof(b->state); change = SCB_BRIDGE_STATE;
        b->last_state = now;
    } else if(!strcmp(kind, "history")) {
        destination = b->history; capacity = sizeof(b->history); change = SCB_BRIDGE_HISTORY;
    } else if(!strcmp(kind, "review")) {
        destination = b->review; capacity = sizeof(b->review); change = SCB_BRIDGE_REVIEW;
    }
    if(!destination || strlen(line) >= capacity) return 0;
    snprintf(destination, capacity, "%s", line);
    return change;
}
unsigned ui_bridge_poll(UiBridge *b, uint32_t now) {
    if(b->disabled || !b->extract) return 0;
    unsigned changes = 0;
    if(b->fd < 0 && (uint32_t)(now - b->last_attempt) >= 1000) {
        b->last_attempt = now;
        b->fd = socket(AF_UNIX, SOCK_STREAM, 0);
        if(b->fd < 0) return 0;
        if(fcntl(b->fd, F_SETFL, O_NONBLOCK) < 0) { disconnect(b); return 0; }
#ifdef SO_NOSIGPIPE
        int yes = 1;
        setsockopt(b->fd, SOL_SOCKET, SO_NOSIGPIPE, &yes, sizeof(yes));
#endif
        struct sockaddr_un address;
        memset(&address, 0, sizeof(address));
        address.sun_family = AF_UNIX;
        snprintf(address.sun_path, sizeof(address.sun_path), "%s", b->path);
        if(connect(b->fd, (struct sockaddr *)&address, sizeof(address)) == 0) {
            b->connected = true;
            changes |= SCB_BRIDGE_CONNECTION;
            b->error[0] = '\0';
        } else if(errno == EINPROGRESS) b->connecting = true;
        else disconnect(b);
    }
    if(b->connecting) {
        struct pollfd p = {b->fd, POLLOUT, 0};
        if(poll(&p, 1, 0) > 0) {
            int error = 0;
            socklen_t size = sizeof(error);
            if(getsockopt(b->fd, SOL_SOCKET, SO_ERROR, &error, &size) != 0 || error) disconnect(b);
            else { b->connected = true; b->connecting = false; changes |= SCB_BRIDGE_CONNECTION; }
        }
    }
    if(!b->connected) return changes;
    if(b->outgoing_size) {
#ifdef MSG_NOSIGNAL
        ssize_t n = send(b->fd, b->outgoing, b->outgoing_size, MSG_NOSIGNAL);
#else
        ssize_t n = send(b->fd, b->outgoing, b->outgoing_size, 0);
#endif
        if(n > 0) {
            b->outgoing_size -= (size_t)n;
            memmove(b->outgoing, b->outgoing + n, b->outgoing_size);
        } else if(n < 0 && errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) {
            disconnect(b); return changes | SCB_BRIDGE_CONNECTION;
        }
    }
    for(;;) {
        if(b->incoming_size + 1 >= sizeof(b->incoming)) { disconnect(b); return changes | SCB_BRIDGE_CONNECTION; }
        ssize_t n = recv(b->fd, b->incoming + b->incoming_size, sizeof(b->incoming) - b->incoming_size - 1, 0);
        if(n == 0) { disconnect(b); return changes | SCB_BRIDGE_CONNECTION; }
        if(n < 0) {
            if(errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) break;
            disconnect(b); return changes | SCB_BRIDGE_CONNECTION;
        }
        b->incoming_size += (size_t)n;
        b->incoming[b->incoming_size] = '\0';
        char *newline;
        while((newline = memchr(b->incoming, '\n', b->incoming_size)) != NULL) {
            size_t length = (size_t)(newline - b->incoming);
            *newline = '\0';
            changes |= accept_line(b, b->incoming, now);
            b->incoming_size -= length + 1;
            memmove(b->incoming, newline + 1, b->incoming_size);
            b->incoming[b->incoming_size] = '\0';
        }
    }
    return changes;
}
