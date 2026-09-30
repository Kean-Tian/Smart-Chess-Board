#include "../include/scb/libchess_adapter.h"

#include <stdio.h>
#include <string.h>

int main(void) {
    ScbRulesGame *game = scb_rules_create();
    char input[16];
    char board[256];
    if (game == NULL) {
        fputs("Could not create the chess rules engine.\n", stderr);
        return 1;
    }
    puts("Smart Chessboard rules prototype. Enter UCI moves (e2e4), or 'quit'.");
    scb_rules_board_text(game, board, sizeof(board));
    fputs(board, stdout);

    while (printf("> ") >= 0 && scanf("%15s", input) == 1) {
        if (strcmp(input, "quit") == 0) break;
        if (!scb_rules_play_move(game, input)) {
            puts("Illegal move. Use a legal UCI move, e.g. e2e4 or e7e8q.");
            continue;
        }
        scb_rules_board_text(game, board, sizeof(board));
        fputs(board, stdout);
        if (scb_rules_is_checkmate(game)) {
            printf("Checkmate. %s wins.\n", scb_rules_side_to_move(game) == SCB_RULES_WHITE ? "Black" : "White");
            break;
        }
        if (scb_rules_is_stalemate(game)) {
            puts("Stalemate.");
            break;
        }
        if (scb_rules_is_draw(game)) {
            puts("Draw by repetition or the 50-move rule.");
            break;
        }
        if (scb_rules_is_in_check(game)) puts("Check.");
    }
    scb_rules_destroy(game);
    return 0;
}
