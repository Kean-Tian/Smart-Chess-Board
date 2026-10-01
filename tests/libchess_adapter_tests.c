#include "../include/scb/libchess_adapter.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void require(bool condition, const char *message) {
    if (!condition) {
        fprintf(stderr, "FAIL: %s\n", message);
        exit(1);
    }
}

static void play(ScbRulesGame *game, const char *uci) {
    require(scb_rules_play_move(game, uci), uci);
}

int main(void) {
    ScbRulesGame *game = scb_rules_create();
    require(game != NULL, "create libchess game");
    require(scb_rules_is_legal_move(game, "e2e4"), "accept legal opening move");
    require(!scb_rules_is_legal_move(game, "e2e5"), "reject illegal pawn move");
    char legal_moves[2048];
    require(scb_rules_legal_moves(game, legal_moves, sizeof(legal_moves)) > 0, "list legal moves");
    require(strstr(legal_moves, "e2e4") != NULL, "list opening move");
    require(strstr(legal_moves, "e2e5") == NULL, "exclude illegal opening move");
    play(game, "e2e4");
    require(!scb_rules_is_legal_move(game, "d2d4"), "reject move by the wrong side");
    play(game, "e7e5");

    char board[256];
    require(scb_rules_board_text(game, board, sizeof(board)) > 0, "render board");
    require(strstr(board, "White to move") != NULL, "report side to move");
    scb_rules_destroy(game);

    ScbRulesGame *mate = scb_rules_create();
    require(mate != NULL, "create checkmate game");
    play(mate, "f2f3");
    play(mate, "e7e5");
    play(mate, "g2g4");
    play(mate, "d8h4");
    require(scb_rules_is_in_check(mate), "detect check");
    require(scb_rules_is_checkmate(mate), "detect checkmate");
    scb_rules_destroy(mate);

    ScbRulesGame *special = scb_rules_create();
    require(special != NULL, "create special-moves game");
    const char *moves[] = {"e2e4", "a7a6", "e4e5", "d7d5", "e5d6", "e7e6",
                           "g1f3", "g8f6", "f1e2", "f8e7", "e1g1"};
    for (size_t index = 0; index < sizeof(moves) / sizeof(moves[0]); ++index) {
        if (index == sizeof(moves) / sizeof(moves[0]) - 1) {
            require(scb_rules_legal_moves(special, legal_moves, sizeof(legal_moves)) > 0, "list castle");
            require(strstr(legal_moves, "e1g1") != NULL, "use normal UCI castling move");
        }
        play(special, moves[index]);
    }
    char fen[128];
    require(scb_rules_fen(special, fen, sizeof(fen)) > 0, "export FEN");
    require(strstr(fen, " b ") != NULL, "FEN reports black to move");
    scb_rules_destroy(special);

    ScbRulesGame *promotion = scb_rules_create();
    require(promotion != NULL, "create promotion game");
    const char *promotion_moves[] = {"a2a4", "h7h5", "a4a5", "h5h4", "a5a6",
                                     "h4h3", "a6b7", "h3g2", "b7a8q"};
    for (size_t index = 0; index < sizeof(promotion_moves) / sizeof(promotion_moves[0]); ++index) {
        play(promotion, promotion_moves[index]);
    }
    scb_rules_destroy(promotion);

    ScbRulesGame *draw = scb_rules_create();
    require(draw != NULL, "create repetition game");
    const char *repetition[] = {"g1f3", "g8f6", "f3g1", "f6g8",
                                "g1f3", "g8f6", "f3g1", "f6g8"};
    for (size_t index = 0; index < sizeof(repetition) / sizeof(repetition[0]); ++index) {
        play(draw, repetition[index]);
    }
    require(scb_rules_is_draw(draw), "detect threefold repetition");
    scb_rules_destroy(draw);

    puts("All libchess adapter tests passed.");
    return 0;
}
