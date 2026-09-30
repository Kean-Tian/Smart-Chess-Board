#include "../include/scb/chess.h"

#include <stdio.h>
#include <string.h>

int main(void) {
    ScbChessGame game;
    char input[16];
    char board[256];
    scb_chess_init(&game);
    puts("Smart Chessboard rules prototype. Enter UCI moves (e2e4), or 'quit'.");
    scb_chess_board_text(&game, board, sizeof(board));
    fputs(board, stdout);

    while (printf("> ") >= 0 && scanf("%15s", input) == 1) {
        ScbMove move;
        if (strcmp(input, "quit") == 0) break;
        if (!scb_chess_parse_uci(input, &move) || !scb_chess_make_move(&game, &move)) {
            puts("Illegal move. Use a legal UCI move, e.g. e2e4 or e7e8q.");
            continue;
        }
        scb_chess_board_text(&game, board, sizeof(board));
        fputs(board, stdout);
        if (scb_chess_is_checkmate(&game)) {
            printf("Checkmate. %s wins.\n", scb_chess_side_to_move(&game) == SCB_WHITE ? "Black" : "White");
            break;
        }
        if (scb_chess_is_stalemate(&game)) {
            puts("Stalemate.");
            break;
        }
        if (scb_chess_is_in_check(&game, scb_chess_side_to_move(&game))) puts("Check.");
    }
    return 0;
}
