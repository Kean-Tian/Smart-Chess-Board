#define _DEFAULT_SOURCE

#include "../../include/scb/libchess_adapter.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>

static int open_serial(const char *path) {
    int fd = open(path, O_RDWR | O_NOCTTY | O_SYNC);
    struct termios settings;
    if (fd < 0) return -1;
    if (tcgetattr(fd, &settings) != 0) {
        close(fd);
        return -1;
    }
    settings.c_iflag = IGNPAR;
    settings.c_oflag = 0;
    settings.c_lflag = 0;
    settings.c_cflag &= (tcflag_t)~(CSIZE | PARENB | CSTOPB);
    settings.c_cflag |= CS8 | CLOCAL | CREAD;
#ifdef CRTSCTS
    settings.c_cflag &= (tcflag_t)~CRTSCTS;
#endif
    settings.c_cc[VMIN] = 1;
    settings.c_cc[VTIME] = 0;
    if (cfsetispeed(&settings, B115200) != 0 || cfsetospeed(&settings, B115200) != 0 ||
        tcsetattr(fd, TCSANOW, &settings) != 0) {
        close(fd);
        return -1;
    }
    return fd;
}

static bool is_square_name(const char *name) {
    return name != NULL && name[0] >= 'a' && name[0] <= 'h' &&
           name[1] >= '1' && name[1] <= '8' && name[2] == '\0';
}

static void print_board(const ScbRulesGame *game) {
    char board[256];
    (void)scb_rules_board_text(game, board, sizeof(board));
    fputs(board, stdout);
}

static void process_line(const char *line, ScbRulesGame *game) {
    char prefix[8] = {0};
    char kind[12] = {0};
    if (sscanf(line, "%7s %11s", prefix, kind) != 2 || strcmp(prefix, "SCB1") != 0) {
        fprintf(stderr, "Ignoring unknown serial line: %s\n", line);
        return;
    }
    if (strcmp(kind, "READY") == 0) {
        printf("MCU ready: %s\n", line);
    } else if (strcmp(kind, "SENSOR") == 0) {
        char square[8] = {0};
        int occupied = -1;
        if (sscanf(line, "SCB1 SENSOR %7s %d", square, &occupied) != 2 ||
            !is_square_name(square) || (occupied != 0 && occupied != 1)) {
            fprintf(stderr, "Malformed sensor event: %s\n", line);
            return;
        }
        printf("Sensor %s %s\n", square, occupied ? "occupied" : "empty");
    } else if (strcmp(kind, "MOVE") == 0) {
        char from[8] = {0};
        char to[8] = {0};
        char uci[6];
        if (sscanf(line, "SCB1 MOVE %7s %7s", from, to) != 2 ||
            !is_square_name(from) || !is_square_name(to)) {
            fprintf(stderr, "Malformed move event: %s\n", line);
            return;
        }
        (void)snprintf(uci, sizeof(uci), "%.2s%.2s", from, to);
        if (!scb_rules_play_move(game, uci)) {
            fprintf(stderr, "MCU move rejected by chess rules: %s%s\n", from, to);
            return;
        }
        printf("Accepted physical move %s%s\n", from, to);
        print_board(game);
        if (scb_rules_is_in_check(game)) puts("Check.");
        if (scb_rules_is_checkmate(game)) puts("Checkmate.");
        if (scb_rules_is_stalemate(game)) puts("Stalemate.");
        if (scb_rules_is_draw(game)) puts("Draw by repetition or the 50-move rule.");
    } else {
        fprintf(stderr, "Unknown SCB1 event: %s\n", line);
    }
}

int main(int argc, char **argv) {
    const char *device = argc > 1 ? argv[1] : "/dev/serial0";
    int fd = open_serial(device);
    ScbRulesGame *game;
    char line[97];
    size_t used = 0;
    if (fd < 0) {
        fprintf(stderr, "Cannot open serial device %s: %s\n", device, strerror(errno));
        return 1;
    }
    game = scb_rules_create();
    if (game == NULL) {
        fputs("Could not create the chess rules engine.\n", stderr);
        close(fd);
        return 1;
    }
    printf("Listening on %s at 115200 baud. Press Ctrl+C to exit.\n", device);
    for (;;) {
        char byte;
        ssize_t count = read(fd, &byte, 1);
        if (count < 0) {
            if (errno == EINTR) continue;
            fprintf(stderr, "Serial read failed: %s\n", strerror(errno));
            scb_rules_destroy(game);
            close(fd);
            return 1;
        }
        if (count == 0) continue;
        if (byte == '\n') {
            if (used > 0 && line[used - 1] == '\r') --used;
            line[used] = '\0';
            process_line(line, game);
            used = 0;
        } else if (used < sizeof(line) - 1) {
            line[used++] = byte;
        } else {
            used = 0;
            fprintf(stderr, "Discarded oversized serial line.\n");
        }
    }
}
